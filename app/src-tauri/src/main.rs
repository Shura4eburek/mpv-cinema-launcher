// Окно без консоли в релизной сборке.
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

mod backend;
mod player_surface;

use backend::{Backend, CallError, LaunchConfig};
use serde_json::{json, Value};
use std::path::PathBuf;
use tauri::path::BaseDirectory;
use tauri::{AppHandle, Emitter, Manager, RunEvent, WindowEvent};

const BACKEND_EVENT: &str = "backend-event";

/// Вызов метода протокола. Проверка данных находится в backend.
#[tauri::command]
async fn backend_call(
    backend: tauri::State<'_, Backend>,
    method: String,
    params: Value,
) -> Result<Value, CallError> {
    let backend = backend.inner().clone();
    tauri::async_runtime::spawn_blocking(move || backend.call(&method, params))
        .await
        .map_err(|_| CallError::new("internal", "Внутренняя ошибка"))?
}

fn launch_config(app: &AppHandle) -> tauri::Result<LaunchConfig> {
    let log_file = app.path().app_log_dir()?.join("backend.log");

    let name = if cfg!(windows) { "mpv-cinema-backend.exe" } else { "mpv-cinema-backend" };
    let bundled = app
        .path()
        .resolve(format!("backend/{name}"), BaseDirectory::Resource)
        .ok()
        .filter(|path| path.is_file());

    Ok(match bundled {
        Some(program) => LaunchConfig {
            program: backend::plain_path(program),
            args: vec![],
            python_path: None,
            log_file,
        },
        None => LaunchConfig {
            // Разработка: исходники Python рядом с приложением.
            program: PathBuf::from("python"),
            args: vec!["-m".into(), "mpv_launcher.backend".into()],
            python_path: Some(PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../src")),
            log_file,
        },
    })
}

fn main() {
    let app = tauri::Builder::default()
        .invoke_handler(tauri::generate_handler![
            backend_call,
            player_surface::player_surface_create,
            player_surface::player_surface_show,
            player_surface::player_surface_move,
            player_surface::player_surface_hide,
            player_surface::player_surface_fullscreen,
        ])
        .on_window_event(|window, event| {
            if let (WindowEvent::Resized(_), Some(main)) = (event, window.get_webview_window("main")) {
                player_surface::follow(&main);
            }
            // Остановка backend ждёт закрытия Chrome: окно не должно зависать на это время.
            if let WindowEvent::CloseRequested { api, .. } = event {
                api.prevent_close();
                let _ = window.hide();
                let handle = window.app_handle().clone();
                let backend = handle.state::<Backend>().inner().clone();
                std::thread::spawn(move || {
                    backend.stop();
                    handle.exit(0);
                });
            }
        })
        .setup(|app| {
            let handle = app.handle().clone();
            let backend = Backend::new(launch_config(&handle)?, move |name, data| {
                let _ = handle.emit(BACKEND_EVENT, json!({ "event": name, "data": data }));
            });
            app.manage(backend.clone());
            // Окно открывается сразу, а backend запускается в фоне.
            tauri::async_runtime::spawn_blocking(move || {
                if backend.ensure_started().is_err() {
                    eprintln!("backend не запустился");
                }
            });
            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("не удалось запустить приложение");

    app.run(|handle, event| {
        if let RunEvent::Exit = event {
            handle.state::<Backend>().stop();
        }
    });
}
