//! Область видео: дочернее окно, в которое mpv рисует через `--wid`. Только Windows.
//! Обычные (не async) команды Tauri выполняются в главном потоке, где и должны жить окна.

use serde::Deserialize;
use tauri::WebviewWindow;

/// Положение области в клиентской части окна, в точках CSS. Выше `clip_top` видео не рисуется.
#[derive(Clone, Copy, Debug, Deserialize)]
pub struct SurfaceRect {
    pub x: f64,
    pub y: f64,
    pub width: f64,
    pub height: f64,
    pub clip_top: f64,
}

#[cfg(windows)]
mod imp {
    use super::SurfaceRect;
    use std::ptr::{null, null_mut};
    use std::sync::atomic::{AtomicBool, AtomicIsize, Ordering};
    use std::sync::Mutex;
    use tauri::WebviewWindow;
    use windows_sys::Win32::Foundation::{HWND, LPARAM, LRESULT, RECT, WPARAM};
    use windows_sys::Win32::Graphics::Gdi::{CreateRectRgn, GetStockObject, SetWindowRgn, BLACK_BRUSH};
    use windows_sys::Win32::System::LibraryLoader::GetModuleHandleW;
    use windows_sys::Win32::UI::WindowsAndMessaging::{
        CreateWindowExW, DefWindowProcW, GetClientRect, GetWindow, IsWindowVisible, LoadCursorW,
        PostMessageW, RegisterClassW, SetForegroundWindow, SetWindowPos, ShowWindow, GW_CHILD, HWND_TOP,
        IDC_ARROW, SWP_NOACTIVATE, SWP_NOZORDER, SWP_SHOWWINDOW, SW_HIDE, WM_LBUTTONDOWN,
        WM_MBUTTONDOWN, WM_MOUSEMOVE, WM_RBUTTONDOWN, WNDCLASSW, WS_CHILD, WS_CLIPCHILDREN,
        WS_CLIPSIBLINGS,
    };
    use windows_sys::Win32::UI::Input::KeyboardAndMouse::{EnableWindow, SetFocus};

    static SURFACE: AtomicIsize = AtomicIsize::new(0);
    // Область на всё окно следует за окном сама, а на странице ей управляет интерфейс.
    static FILLS_WINDOW: AtomicBool = AtomicBool::new(false);
    // Текущий регион обрезки: скрыто строк сверху, ширина, высота.
    static CLIP: Mutex<(i32, i32, i32)> = Mutex::new((0, 0, 0));

    /// mpv отключает своё встроенное окно, чтобы мышь получал родитель. Как только мышь пришла сюда,
    /// окно включается: дальше мышь, клавиши и отслеживание курсора работают в нём как в обычном режиме.
    unsafe extern "system" fn surface_proc(hwnd: HWND, message: u32, wparam: WPARAM, lparam: LPARAM) -> LRESULT {
        if matches!(message, WM_MOUSEMOVE | WM_LBUTTONDOWN | WM_RBUTTONDOWN | WM_MBUTTONDOWN) {
            let player = GetWindow(hwnd, GW_CHILD);
            if !player.is_null() {
                EnableWindow(player, 1);
                SetFocus(player);
                PostMessageW(player, message, wparam, lparam);
                return 0;
            }
        }
        DefWindowProcW(hwnd, message, wparam, lparam)
    }

    fn wide(text: &str) -> Vec<u16> {
        text.encode_utf16().chain(std::iter::once(0)).collect()
    }

    fn parent_of(window: &WebviewWindow) -> Result<HWND, String> {
        Ok(window.hwnd().map_err(|error| error.to_string())?.0 as HWND)
    }

    pub fn create(window: &WebviewWindow) -> Result<isize, String> {
        let existing = SURFACE.load(Ordering::SeqCst);
        if existing != 0 {
            return Ok(existing);
        }
        let parent = parent_of(window)?;
        let class = wide("MpvCinemaSurface");
        // SAFETY: строки живут до конца вызовов, родитель существует, вызов идёт в главном потоке.
        let surface = unsafe {
            let instance = GetModuleHandleW(null());
            let mut description: WNDCLASSW = std::mem::zeroed();
            description.lpfnWndProc = Some(surface_proc);
            description.hCursor = LoadCursorW(null_mut(), IDC_ARROW);
            description.hInstance = instance;
            description.hbrBackground = GetStockObject(BLACK_BRUSH) as _;
            description.lpszClassName = class.as_ptr();
            RegisterClassW(&description);
            CreateWindowExW(
                0,
                class.as_ptr(),
                null(),
                WS_CHILD | WS_CLIPSIBLINGS | WS_CLIPCHILDREN,
                0,
                0,
                0,
                0,
                parent,
                null_mut(),
                instance,
                null(),
            )
        };
        if surface.is_null() {
            return Err("не удалось создать область видео".into());
        }
        SURFACE.store(surface as isize, Ordering::SeqCst);
        Ok(surface as isize)
    }

    fn client_size(parent: HWND) -> (i32, i32) {
        let mut rect = RECT { left: 0, top: 0, right: 0, bottom: 0 };
        // SAFETY: rect живёт до конца вызова; при ошибке остаётся нулевой размер.
        unsafe { GetClientRect(parent, &mut rect) };
        (rect.right - rect.left, rect.bottom - rect.top)
    }

    /// Область на всё окно: полный экран.
    fn fill_window(window: &WebviewWindow) -> Result<(), String> {
        let surface = create(window)? as HWND;
        FILLS_WINDOW.store(true, Ordering::SeqCst);
        *CLIP.lock().map_err(|error| error.to_string())? = (0, 0, 0);
        let (width, height) = client_size(parent_of(window)?);
        // SAFETY: окно создано этим модулем и живёт до закрытия приложения.
        unsafe {
            SetWindowRgn(surface, null_mut(), 1);
            SetWindowPos(surface, HWND_TOP, 0, 0, width, height, SWP_SHOWWINDOW | SWP_NOACTIVATE);
        }
        Ok(())
    }

    pub fn fullscreen(window: &WebviewWindow, on: bool) -> Result<(), String> {
        window.set_fullscreen(on).map_err(|error| error.to_string())?;
        if on {
            fill_window(window)?;
        }
        // При выходе страница сразу возвращает области прежнее место.
        focus_player(window);
        Ok(())
    }

    fn apply_rect(window: &WebviewWindow, rect: SurfaceRect, extra_flags: u32) -> Result<(), String> {
        let surface = create(window)? as HWND;
        FILLS_WINDOW.store(false, Ordering::SeqCst);
        let scale = window.scale_factor().map_err(|error| error.to_string())?;
        let (x, y) = ((rect.x * scale).round() as i32, (rect.y * scale).round() as i32);
        let (width, height) = ((rect.width * scale).round() as i32, (rect.height * scale).round() as i32);
        let hidden = (((rect.clip_top - rect.y) * scale).round() as i32).clamp(0, height);
        // Без обрезки регион не нужен, и размер окна на него не влияет.
        let clip = if hidden > 0 { (hidden, width, height) } else { (0, 0, 0) };
        let mut current = CLIP.lock().map_err(|error| error.to_string())?;
        // SAFETY: окно создано этим модулем; регион переходит во владение окна.
        unsafe {
            // Шапка приложения лежит ниже дочернего окна, поэтому верх видео обрезается регионом.
            if *current != clip {
                *current = clip;
                let region = if hidden > 0 { CreateRectRgn(0, hidden, width, height) } else { null_mut() };
                SetWindowRgn(surface, region, 1);
            }
            SetWindowPos(surface, HWND_TOP, x, y, width, height, SWP_NOACTIVATE | extra_flags);
        }
        Ok(())
    }

    pub fn show_at(window: &WebviewWindow, rect: SurfaceRect) -> Result<(), String> {
        apply_rect(window, rect, SWP_SHOWWINDOW)?;
        focus_player(window);
        Ok(())
    }

    pub fn move_to(window: &WebviewWindow, rect: SurfaceRect) -> Result<(), String> {
        apply_rect(window, rect, 0)
    }

    pub fn hide(window: &WebviewWindow) -> Result<(), String> {
        let surface = SURFACE.load(Ordering::SeqCst);
        if surface != 0 {
            // SAFETY: окно создано этим модулем и живёт до закрытия приложения.
            unsafe { ShowWindow(surface as HWND, SW_HIDE) };
            // Клавиши снова должны идти в страницу.
            window.set_focus().map_err(|error| error.to_string())?;
        }
        Ok(())
    }

    /// Вернуть клавиатуру в плеер, если её забрало другое окно приложения.
    pub fn focus_player(window: &WebviewWindow) {
        let surface = SURFACE.load(Ordering::SeqCst) as HWND;
        let Ok(parent) = parent_of(window) else { return };
        // SAFETY: вызов идёт в главном потоке; окна существуют, проверка на null выполняется.
        unsafe {
            SetForegroundWindow(parent);
            if !surface.is_null() {
                let player = GetWindow(surface, GW_CHILD);
                if !player.is_null() {
                    EnableWindow(player, 1);
                    SetFocus(player);
                }
            }
        }
    }

    /// Вызывается при изменении размера окна приложения.
    pub fn follow(window: &WebviewWindow) {
        let surface = SURFACE.load(Ordering::SeqCst) as HWND;
        let Ok(parent) = parent_of(window) else { return };
        // SAFETY: проверка окна на null выполняется до вызова; окно живёт до закрытия приложения.
        unsafe {
            if !surface.is_null() && FILLS_WINDOW.load(Ordering::SeqCst) && IsWindowVisible(surface) != 0 {
                let (width, height) = client_size(parent);
                SetWindowPos(surface, null_mut(), 0, 0, width, height, SWP_NOZORDER | SWP_NOACTIVATE);
            }
        }
    }
}

#[cfg(windows)]
pub use imp::{create, follow, fullscreen, hide, move_to, show_at};

#[cfg(not(windows))]
mod imp {
    use super::SurfaceRect;
    use tauri::WebviewWindow;

    const UNSUPPORTED: &str = "unsupported";

    pub fn show_at(_window: &WebviewWindow, _rect: SurfaceRect) -> Result<(), String> {
        Err(UNSUPPORTED.into())
    }

    pub fn move_to(_window: &WebviewWindow, _rect: SurfaceRect) -> Result<(), String> {
        Err(UNSUPPORTED.into())
    }

    pub fn fullscreen(_window: &WebviewWindow, _on: bool) -> Result<(), String> {
        Err(UNSUPPORTED.into())
    }

    pub fn create(_window: &WebviewWindow) -> Result<isize, String> {
        Err(UNSUPPORTED.into())
    }

    pub fn hide(_window: &WebviewWindow) -> Result<(), String> {
        Err(UNSUPPORTED.into())
    }

    pub fn follow(_window: &WebviewWindow) {}
}

#[cfg(not(windows))]
pub use imp::{create, follow, fullscreen, hide, move_to, show_at};

#[tauri::command]
pub fn player_surface_create(window: WebviewWindow) -> Result<isize, String> {
    create(&window)
}

#[tauri::command]
pub fn player_surface_show(window: WebviewWindow, rect: SurfaceRect) -> Result<(), String> {
    show_at(&window, rect)
}

#[tauri::command]
pub fn player_surface_move(window: WebviewWindow, rect: SurfaceRect) -> Result<(), String> {
    move_to(&window, rect)
}

#[tauri::command]
pub fn player_surface_hide(window: WebviewWindow) -> Result<(), String> {
    hide(&window)
}

#[tauri::command]
pub fn player_surface_fullscreen(window: WebviewWindow, on: bool) -> Result<(), String> {
    fullscreen(&window, on)
}
