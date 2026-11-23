"""T008 [US1] (001) + T006 (002): запуск mpv / dry-run / поиск mpv."""

from types import SimpleNamespace
from unittest import mock

from mpv_launcher import runner
from mpv_launcher.cli import EXIT_NO_MPV, EXIT_OK
from mpv_launcher.presets import LaunchPlan


def test_dry_run_prints_and_does_not_launch(capsys):
    plan = LaunchPlan(mpv_args=["mpv", "--profile=gpu-hq", "https://h/x"])
    with mock.patch.object(runner.subprocess, "run") as run_mock:
        code = runner.run(plan, dry_run=True)
    assert code == EXIT_OK
    run_mock.assert_not_called()
    assert "https://h/x" in capsys.readouterr().out


def test_missing_mpv_returns_code_and_skips_launch(capsys):
    plan = LaunchPlan(mpv_args=["mpv", "https://h/x"])
    with mock.patch.object(runner.locate, "find_mpv", return_value=None), \
        mock.patch.object(runner.subprocess, "run") as run_mock:
        code = runner.run(plan, dry_run=False)
    assert code == EXIT_NO_MPV
    run_mock.assert_not_called()
    assert "mpv не найден" in capsys.readouterr().err


def _run_fallback(returncodes, **kwargs):
    plan = LaunchPlan(mpv_args=["mpv", "--demuxer=lavf", "https://a/x"])
    results = [SimpleNamespace(returncode=c) for c in returncodes]
    with mock.patch.object(runner.locate, "find_mpv", return_value="mpv"), \
        mock.patch.object(runner.subprocess, "run", side_effect=results) as run_mock:
        code = runner.run_with_fallback(plan, ["https://b/x"], **kwargs)
    return code, [call.args[0] for call in run_mock.call_args_list]


def test_fallback_tries_next_mirror_when_load_fails():
    code, calls = _run_fallback([runner.MPV_EXIT_LOAD_FAILED, 0])
    assert code == 0
    assert calls == [
        ["mpv", "--demuxer=lavf", "https://a/x"],
        ["mpv", "--demuxer=lavf", "https://b/x"],
    ]


def test_fallback_not_used_after_normal_exit():
    code, calls = _run_fallback([0])
    assert code == 0
    assert len(calls) == 1


def test_fallback_reports_failure_when_all_mirrors_fail():
    code, calls = _run_fallback([runner.MPV_EXIT_LOAD_FAILED] * 2)
    assert code == runner.MPV_EXIT_LOAD_FAILED
    assert len(calls) == 2


def test_fallback_log_has_host_only_and_notifies(capsys):
    plan = LaunchPlan(mpv_args=["mpv", "https://a/x"])
    seen = []
    results = [SimpleNamespace(returncode=runner.MPV_EXIT_LOAD_FAILED), SimpleNamespace(returncode=0)]
    with mock.patch.object(runner.locate, "find_mpv", return_value="mpv"), \
        mock.patch.object(runner.subprocess, "run", side_effect=results):
        runner.run_with_fallback(plan, ["https://b.test/SECRET/x"], on_fallback=seen.append)
    err = capsys.readouterr().err
    assert "b.test" in err and "SECRET" not in err
    assert seen == ["https://b.test/SECRET/x"]


def test_process_is_given_to_caller_and_exit_code_returned():
    plan = LaunchPlan(mpv_args=["mpv", "https://a/x"])
    process = mock.Mock()
    process.wait.return_value = 0
    seen = []
    with mock.patch.object(runner.locate, "find_mpv", return_value="mpv"), \
        mock.patch.object(runner.subprocess, "Popen", return_value=process):
        assert runner.run(plan, on_process=seen.append) == 0
    assert seen == [process]


def test_cancelled_start_does_not_try_next_mirror():
    plan = LaunchPlan(mpv_args=["mpv", "https://a/x"])
    with mock.patch.object(runner.locate, "find_mpv", return_value="mpv"), \
        mock.patch.object(runner.subprocess, "run", return_value=SimpleNamespace(returncode=runner.MPV_EXIT_LOAD_FAILED)) as run_mock:
        runner.run_with_fallback(plan, ["https://b/x"], should_stop=lambda: True)
    assert run_mock.call_count == 1


def test_console_wrapper_is_replaced_with_player(tmp_path):
    wrapper = tmp_path / "mpv.com"
    player = tmp_path / "mpv.exe"
    wrapper.write_text("")
    player.write_text("")
    assert runner._player_binary(str(wrapper)) == str(player)
    assert runner._player_binary(str(player)) == str(player)
    assert runner._player_binary(str(tmp_path / "other.com")) == str(tmp_path / "other.com")


def test_launches_resolved_mpv_path():
    plan = LaunchPlan(mpv_args=["mpv", "--profile=gpu-hq", "https://h/x"])
    with mock.patch.object(runner.locate, "find_mpv", return_value="/opt/homebrew/bin/mpv"), \
        mock.patch.object(runner.subprocess, "run",
                          return_value=SimpleNamespace(returncode=0)) as run_mock:
        code = runner.run(plan, dry_run=False)
    assert code == 0
    # argv[0] заменён на разрешённый путь, остальное — из плана
    run_mock.assert_called_once_with(
        ["/opt/homebrew/bin/mpv", "--profile=gpu-hq", "https://h/x"]
    )
