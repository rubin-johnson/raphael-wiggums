from click.testing import CliRunner
from raphael import cli


def test_cli_has_generate_command():
    runner = CliRunner()
    result = runner.invoke(cli, ["generate", "--help"])
    assert result.exit_code == 0


def test_cli_has_execute_command():
    runner = CliRunner()
    result = runner.invoke(cli, ["execute", "--help"])
    assert result.exit_code == 0
