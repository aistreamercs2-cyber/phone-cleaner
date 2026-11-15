from phone_cleaner import parsers
from phone_cleaner.adb import parse_shell_command
from phone_cleaner.adb_installer import _os_key


def test_parse_devices():
    out = """List of devices attached
R58M12345\tdevice product:beyond1lte model:SM_G973F device:beyond1 transport_id:1
emulator-5554\tunauthorized transport_id:2
"""
    devices = parsers.parse_devices(out)
    assert len(devices) == 2
    assert devices[0].serial == "R58M12345"
    assert devices[0].is_ready
    assert devices[0].props["model"] == "SM_G973F"
    assert devices[0].model == "SM G973F"
    assert not devices[1].is_ready


def test_parse_getprop():
    out = "[ro.product.model]: [Pixel 7]\n[ro.build.version.release]: [14]\n"
    props = parsers.parse_getprop(out)
    assert props["ro.product.model"] == "Pixel 7"
    assert props["ro.build.version.release"] == "14"


def test_parse_pm_list():
    out = "package:/system/app/Settings/Settings.apk=com.android.settings\npackage:com.example.app\n"
    rows = parsers.parse_pm_list(out)
    assert rows[0] == ("com.android.settings", "/system/app/Settings/Settings.apk")
    assert rows[1] == ("com.example.app", None)


def test_parse_diskstats():
    out = (
        "Package Names: [\"com.a\", \"com.b\"]\n"
        "App Sizes: [1024, 2048]\n"
        "App Data Sizes: [4096, 8192]\n"
        "Cache Sizes: [512, 0]\n"
    )
    sizes = parsers.parse_diskstats(out)
    assert sizes["com.a"] == {"app": 1024, "data": 4096, "cache": 512}
    assert sizes["com.b"]["data"] == 8192


def test_human_size_and_parse_size():
    assert parsers.human_size(1024) == "1.0 КБ"
    assert parsers.human_size(0) == "0 Б"
    assert parsers.parse_size_text("12.3M") == 12897484


def test_parse_df_and_battery():
    df = "Filesystem Size Used Avail Use% Mounted on\n/dev/block/dm-5 108G 71G 37G 66% /data\n"
    rows = parsers.parse_df(df)
    assert rows[0]["mounted"] == "/data"
    assert rows[0]["use"] == "66%"
    battery = parsers.parse_battery("  level: 87\n  temperature: 311\n")
    assert battery["level"] == "87"


def test_parse_shell_command():
    assert parse_shell_command("pm list packages -3") == ["shell", "pm", "list", "packages", "-3"]
    assert parse_shell_command("shell ls /sdcard") == ["shell", "ls", "/sdcard"]
    assert parse_shell_command("") == []
    assert parse_shell_command("reboot recovery") == ["reboot", "recovery"]


def test_os_key():
    assert _os_key() in {"windows", "linux", "darwin"}
