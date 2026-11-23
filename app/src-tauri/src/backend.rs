//! Запуск Python-backend и обмен строками JSON (specs/003-app-player-ui/contracts/backend-protocol.md).

use serde_json::{json, Value};
use std::collections::HashMap;
use std::fs::{self, File, OpenOptions};
use std::io::{self, BufRead, BufReader, Write};
use std::path::{Path, PathBuf};
use std::process::{Child, ChildStdin, Command, Stdio};
use std::sync::mpsc::{channel, Sender};
use std::sync::{Arc, Mutex};
use std::thread;
use std::time::{Duration, Instant};

const STOP_TIMEOUT: Duration = Duration::from_secs(5);
const RESTARTS_ALLOWED: u32 = 1;

/// Ошибка вызова в том же виде, что и в протоколе.
#[derive(Debug, Clone, PartialEq, serde::Serialize)]
pub struct CallError {
    pub code: String,
    pub message: String,
}

impl CallError {
    pub fn new(code: &str, message: &str) -> Self {
        Self { code: code.into(), message: message.into() }
    }

    fn backend_down() -> Self {
        Self::new("backend_down", "Фоновый процесс недоступен")
    }
}

pub type CallResult = Result<Value, CallError>;

/// Разобранная строка от backend.
#[derive(Debug, PartialEq)]
pub enum Incoming {
    Response { id: u64, result: CallResult },
    Event { name: String, data: Value },
}

pub fn encode_request(id: u64, method: &str, params: &Value) -> String {
    let mut line = json!({ "id": id, "method": method, "params": params }).to_string();
    line.push('\n');
    line
}

/// None — строка не относится к протоколу; такие строки пропускаются.
pub fn parse_line(line: &str) -> Option<Incoming> {
    let value: Value = serde_json::from_str(line.trim()).ok()?;

    if let Some(name) = value.get("event").and_then(Value::as_str) {
        return Some(Incoming::Event {
            name: name.to_string(),
            data: value.get("data").cloned().unwrap_or(Value::Null),
        });
    }

    let id = value.get("id")?.as_u64()?;
    if let Some(error) = value.get("error") {
        let text = |key: &str| error.get(key).and_then(Value::as_str).unwrap_or("").to_string();
        return Some(Incoming::Response {
            id,
            result: Err(CallError { code: text("code"), message: text("message") }),
        });
    }
    Some(Incoming::Response { id, result: Ok(value.get("result")?.clone()) })
}

/// Открытые запросы, ожидающие ответа.
#[derive(Default)]
pub struct Pending(HashMap<u64, Sender<CallResult>>);

impl Pending {
    pub fn insert(&mut self, id: u64, sender: Sender<CallResult>) {
        self.0.insert(id, sender);
    }

    pub fn remove(&mut self, id: u64) {
        self.0.remove(&id);
    }

    pub fn resolve(&mut self, id: u64, result: CallResult) {
        if let Some(sender) = self.0.remove(&id) {
            let _ = sender.send(result);
        }
    }

    pub fn fail_all(&mut self, error: CallError) {
        for (_, sender) in self.0.drain() {
            let _ = sender.send(Err(error.clone()));
        }
    }
}

/// Убрать префикс `\\?\`: путь передаётся дальше в Python и аргументы mpv.
pub fn plain_path(path: PathBuf) -> PathBuf {
    match path.to_str().and_then(|text| text.strip_prefix(r"\\?\")) {
        Some(plain) if !plain.starts_with("UNC\\") => PathBuf::from(plain),
        _ => path,
    }
}

/// Как запускать backend: собранный файл или Python при разработке.
#[derive(Clone, Debug)]
pub struct LaunchConfig {
    pub program: PathBuf,
    pub args: Vec<String>,
    pub python_path: Option<PathBuf>,
    pub log_file: PathBuf,
}

struct Running {
    child: Child,
    stdin: ChildStdin,
}

struct State {
    running: Option<Running>,
    next_id: u64,
    generation: u64,
    restarts_left: u32,
    stopping: bool,
}

type EventSink = Arc<dyn Fn(&str, Value) + Send + Sync>;

/// Управление процессом. Дешёвое клонирование: все копии разделяют одно состояние.
#[derive(Clone)]
pub struct Backend {
    config: LaunchConfig,
    state: Arc<Mutex<State>>,
    pending: Arc<Mutex<Pending>>,
    sink: EventSink,
}

impl Backend {
    pub fn new(config: LaunchConfig, sink: impl Fn(&str, Value) + Send + Sync + 'static) -> Self {
        Self {
            config,
            state: Arc::new(Mutex::new(State {
                running: None,
                next_id: 1,
                generation: 0,
                restarts_left: RESTARTS_ALLOWED,
                stopping: false,
            })),
            pending: Arc::new(Mutex::new(Pending::default())),
            sink: Arc::new(sink),
        }
    }

    /// Запустить процесс, если он ещё не запущен. Безопасно вызывать повторно.
    pub fn ensure_started(&self) -> io::Result<()> {
        let mut state = self.state.lock().unwrap();
        if state.running.is_some() || state.stopping {
            return Ok(());
        }
        self.spawn_locked(&mut state)
    }

    fn spawn_locked(&self, state: &mut State) -> io::Result<()> {
        let log = open_log(&self.config.log_file)?;
        let mut command = Command::new(&self.config.program);
        command
            .args(&self.config.args)
            .env("PYTHONUTF8", "1")
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::piped());
        if let Some(path) = &self.config.python_path {
            command.env("PYTHONPATH", path);
        }
        hide_console(&mut command);

        let mut child = command.spawn()?;
        let stdin = child.stdin.take().expect("stdin перенаправлен");
        let stdout = child.stdout.take().expect("stdout перенаправлен");
        let stderr = child.stderr.take().expect("stderr перенаправлен");

        state.generation += 1;
        let generation = state.generation;
        state.running = Some(Running { child, stdin });

        // stderr читается постоянно, иначе заполненный канал остановит Python.
        thread::spawn(move || copy_lines(stderr, log));

        let this = self.clone();
        thread::spawn(move || {
            for line in BufReader::new(stdout).lines() {
                let Ok(line) = line else { break };
                this.dispatch(&line);
            }
            this.on_exit(generation);
        });
        Ok(())
    }

    fn dispatch(&self, line: &str) {
        match parse_line(line) {
            Some(Incoming::Response { id, result }) => {
                self.state.lock().unwrap().restarts_left = RESTARTS_ALLOWED;
                self.pending.lock().unwrap().resolve(id, result);
            }
            Some(Incoming::Event { name, data }) => (self.sink)(&name, data),
            None => {}
        }
    }

    fn on_exit(&self, generation: u64) {
        let mut state = self.state.lock().unwrap();
        // Устаревший поток чтения не должен трогать уже новый процесс.
        if state.generation != generation {
            return;
        }
        if let Some(mut running) = state.running.take() {
            let _ = running.child.wait();
        }
        if state.stopping {
            return;
        }
        self.pending.lock().unwrap().fail_all(CallError::backend_down());

        let restarted = state.restarts_left > 0 && {
            state.restarts_left -= 1;
            self.spawn_locked(&mut state).is_ok()
        };
        drop(state);
        if !restarted {
            (self.sink)("backend_down", Value::Null);
        }
    }

    /// Выполнить запрос и дождаться ответа. Вызывать вне основного потока.
    pub fn call(&self, method: &str, params: Value) -> CallResult {
        let (sender, receiver) = channel();
        {
            let mut state = self.state.lock().unwrap();
            if state.running.is_none() && !state.stopping {
                // «Повторить» после отказа: новый запрос даёт процессу ещё одну попытку.
                state.restarts_left = RESTARTS_ALLOWED;
                self.spawn_locked(&mut state).map_err(|_| CallError::backend_down())?;
            }
            let id = state.next_id;
            state.next_id += 1;
            self.pending.lock().unwrap().insert(id, sender);

            let line = encode_request(id, method, &params);
            let written = state
                .running
                .as_mut()
                .ok_or_else(CallError::backend_down)
                .and_then(|r| write_line(&mut r.stdin, &line).map_err(|_| CallError::backend_down()));
            if let Err(error) = written {
                self.pending.lock().unwrap().remove(id);
                return Err(error);
            }
        }
        receiver.recv().unwrap_or_else(|_| Err(CallError::backend_down()))
    }

    /// Закрыть stdin и дать процессу завершить Chrome; затем снять принудительно.
    pub fn stop(&self) {
        let running = {
            let mut state = self.state.lock().unwrap();
            state.stopping = true;
            state.running.take()
        };
        self.pending.lock().unwrap().fail_all(CallError::backend_down());
        let Some(Running { mut child, stdin }) = running else { return };
        drop(stdin);

        let deadline = Instant::now() + STOP_TIMEOUT;
        while Instant::now() < deadline {
            if matches!(child.try_wait(), Ok(Some(_))) {
                return;
            }
            thread::sleep(Duration::from_millis(50));
        }
        let _ = child.kill();
        let _ = child.wait();
    }
}

fn write_line(stdin: &mut ChildStdin, line: &str) -> io::Result<()> {
    stdin.write_all(line.as_bytes())?;
    stdin.flush()
}

fn open_log(path: &Path) -> io::Result<File> {
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent)?;
    }
    OpenOptions::new().create(true).append(true).open(path)
}

fn copy_lines(source: impl io::Read, mut log: File) {
    let _ = io::copy(&mut BufReader::new(source), &mut log);
}

#[cfg(windows)]
fn hide_console(command: &mut Command) {
    use std::os::windows::process::CommandExt;
    const CREATE_NO_WINDOW: u32 = 0x0800_0000;
    command.creation_flags(CREATE_NO_WINDOW);
}

#[cfg(not(windows))]
fn hide_console(_command: &mut Command) {}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn removes_verbatim_prefix_but_keeps_network_paths() {
        assert_eq!(plain_path(PathBuf::from(r"\\?\C:\App\b.exe")), PathBuf::from(r"C:\App\b.exe"));
        assert_eq!(plain_path(PathBuf::from(r"C:\App\b.exe")), PathBuf::from(r"C:\App\b.exe"));
        assert_eq!(plain_path(PathBuf::from(r"\\?\UNC\srv\b.exe")), PathBuf::from(r"\\?\UNC\srv\b.exe"));
    }

    #[test]
    fn encodes_one_line_with_id_method_and_params() {
        let line = encode_request(7, "search", &json!({ "query": "Тенет" }));
        assert!(line.ends_with('\n'));
        assert_eq!(line.matches('\n').count(), 1);
        let value: Value = serde_json::from_str(&line).unwrap();
        assert_eq!(value["id"], 7);
        assert_eq!(value["method"], "search");
        assert_eq!(value["params"]["query"], "Тенет");
    }

    #[test]
    fn parses_success_response() {
        assert_eq!(
            parse_line(r#"{"id": 3, "result": {"ok": true}}"#),
            Some(Incoming::Response { id: 3, result: Ok(json!({ "ok": true })) })
        );
    }

    #[test]
    fn parses_null_result_as_success() {
        assert_eq!(
            parse_line(r#"{"id": 3, "result": null}"#),
            Some(Incoming::Response { id: 3, result: Ok(Value::Null) })
        );
    }

    #[test]
    fn parses_error_response() {
        assert_eq!(
            parse_line(r#"{"id": 4, "error": {"code": "network", "message": "x"}}"#),
            Some(Incoming::Response { id: 4, result: Err(CallError::new("network", "x")) })
        );
    }

    #[test]
    fn parses_event() {
        assert_eq!(
            parse_line(r#"{"event": "playback_finished", "data": {"code": 0}}"#),
            Some(Incoming::Event { name: "playback_finished".into(), data: json!({ "code": 0 }) })
        );
    }

    #[test]
    fn skips_foreign_lines() {
        for line in ["not json", "[1,2]", "{}", r#"{"id": null, "error": {}}"#, r#"{"id": 1}"#] {
            assert_eq!(parse_line(line), None, "{line}");
        }
    }

    #[test]
    fn answers_may_arrive_in_any_order() {
        let mut pending = Pending::default();
        let (first_tx, first_rx) = channel();
        let (second_tx, second_rx) = channel();
        pending.insert(1, first_tx);
        pending.insert(2, second_tx);

        pending.resolve(2, Ok(json!("second")));
        pending.resolve(1, Ok(json!("first")));
        pending.resolve(99, Ok(json!("nobody")));

        assert_eq!(first_rx.recv().unwrap(), Ok(json!("first")));
        assert_eq!(second_rx.recv().unwrap(), Ok(json!("second")));
    }

    #[test]
    fn fail_all_finishes_every_open_request() {
        let mut pending = Pending::default();
        let (tx, rx) = channel();
        pending.insert(1, tx);
        pending.fail_all(CallError::backend_down());
        assert_eq!(rx.recv().unwrap().unwrap_err().code, "backend_down");
    }
}
