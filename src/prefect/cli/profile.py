"""
Command line interface for working with profiles
"""
import os
from typing import List

import textwrap
import toml
import typer

import prefect.context
import prefect.settings
from prefect.cli.base import (
    PrefectTyper,
    app,
    console,
    exit_with_error,
    exit_with_success,
)

profile_app = PrefectTyper(
    name="profile", help="Commands for interacting with your Prefect profiles."
)
app.add_typer(profile_app)


@profile_app.command()
def get(names: List[str] = typer.Argument(None)):
    """
    Show settings in one or many profiles. Defaults to the current profile.
    """
    profiles = prefect.settings.load_profiles()
    if not names:
        profile = prefect.context.get_profile_context()
        names = [profile.name]

    display_profiles = {
        name: values for name, values in profiles.items() if name in names
    }
    console.out(toml.dumps(display_profiles).strip())


@profile_app.command()
def ls():
    """
    List profile names.
    """
    profiles = prefect.settings.load_profiles()
    current = prefect.context.get_profile_context().name
    for name in profiles:
        if name == current:
            console.print(f"* {name}")
        else:
            console.print(name)


@profile_app.command()
def set(variables: List[str]):
    """
    Change the value for a setting.

    Sets the value in the current profile.
    """
    profiles = prefect.settings.load_profiles()
    profile = prefect.context.get_profile_context()
    env = profiles[profile.name]

    parsed_variables = []
    for variable in variables:
        try:
            var, value = variable.split("=")
        except ValueError:
            exit_with_error(
                f"Failed to parse argument {variable!r}. Use the format 'VAR=VAL'."
            )

        parsed_variables.append((var, value))

    for var, value in parsed_variables:
        env[var] = value
        console.print(f"Set variable {var!r} to {value!r}")

    for var, _ in parsed_variables:
        if var in os.environ:
            console.print(
                f"[yellow]{var!r} is also set by an environment variable which will "
                f"override your config value. Run `unset {var}` to clear it."
            )

    prefect.settings.write_profiles(profiles)
    exit_with_success(f"Updated profile {profile.name!r}")


@profile_app.command()
def unset(variables: List[str]):
    """
    Restore the default value for a setting.

    Removes the setting from the current profile.
    """
    profiles = prefect.settings.load_profiles()
    profile = prefect.context.get_profile_context()
    env = profiles[profile.name]

    for var in variables:
        if var not in env:
            exit_with_error(f"Variable {var!r} not found in profile {profile.name!r}.")
        env.pop(var)

    for var in variables:
        console.print(f"Unset variable {var!r}")

    prefect.settings.write_profiles(profiles)
    exit_with_success(f"Updated profile {profile.name!r}")


@profile_app.command()
def create(
    name: str,
    from_name: str = typer.Option(None, "--from", help="Copy an existing profile."),
):
    """
    Create a new profile.
    """

    profiles = prefect.settings.load_profiles()
    if name in profiles:
        console.print(
            textwrap.dedent(
                f"""
                [red]Profile {name!r} already exists.[/red]
                To create a new profile, remove the existing profile first:

                    prefect profile rm {name!r}
                """
            ).strip()
        )
        raise typer.Exit(1)

    if from_name:
        if from_name not in profiles:
            exit_with_error("Profile {from_name!r} not found.")

        profiles[name] = profiles[from_name]
        from_blurb = f" matching {from_name!r}"
    else:
        from_blurb = ""
        profiles[name] = {}

    prefect.settings.write_profiles(profiles)
    loc = prefect.settings.PREFECT_PROFILES_PATH.value()
    console.print(
        textwrap.dedent(
            f"""
            [green]Created profile {name!r}{from_blurb} at {loc}.[/green]
            To use your profile, set an environment variable:

                export PREFECT_PROFILE={name!r}

            or include the profile in your CLI commands:

                prefect -p {name!r} config view
            """
        ).strip()
    )


@profile_app.command()
def rm(name: str):
    """
    Remove the given profile.
    """
    profiles = prefect.settings.load_profiles()
    if name not in profiles:
        exit_with_error(f"Profle {name!r} not found.")

    profiles.pop(name)

    verb = "Removed"
    if name == "default":
        verb = "Reset"
        profiles["default"] = {}

    prefect.settings.write_profiles(profiles)
    exit_with_success(f"{verb} profile {name!r}.")


@profile_app.command()
def rename(name: str, new_name: str):
    """
    Change the name of a profile.
    """
    profiles = prefect.settings.load_profiles()
    if name not in profiles:
        exit_with_error(f"Profle {name!r} not found.")

    if new_name in profiles:
        exit_with_error(f"Profile {new_name!r} already exists.")

    profiles[new_name] = profiles.pop(name)

    prefect.settings.write_profiles(profiles)
    exit_with_success(f"Renamed profile {name!r} to {new_name!r}.")


@profile_app.command()
def inspect(name: str = None, show_defaults: bool = False, show_sources: bool = False):
    """
    Display settings from a given profile; defaults to active.
    """
    if name:
        profiles = prefect.settings.load_profiles()
        if name not in profiles:
            exit_with_error(f"Profle {name!r} not found.")
        current_settings = profiles[name]
    else:
        profile = prefect.context.get_profile_context()
        name = profile.name
        current_settings = profile.settings.dict()

    # Get settings at each level, converted to a flat dictionary for easy comparison
    default_settings = prefect.settings.get_default_settings().dict()
    env_settings = prefect.settings.get_settings_from_env().dict()

    output = [f"PREFECT_PROFILE={name!r}"]

    # Collect differences from defaults set in the env and the profile
    env_overrides = {
        key: val for key, val in env_settings.items() if val != default_settings[key]
    }

    current_overrides = {
        key: val
        for key, val in current_settings.items()
        if val != default_settings[key]
    }

    for key, value in current_overrides.items():
        source = "env" if value == env_overrides.get(key) else "profile"
        source_blurb = f" (from {source})" if show_sources else ""
        output.append(f"{key}='{value}'{source_blurb}")

    if show_defaults:
        for key, value in sorted(default_settings.items()):
            source_blurb = f" (from defaults)" if show_sources else ""
            output.append(f"{key}='{value}'{source_blurb}")

    console.print("\n".join(output))
