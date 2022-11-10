#!/opt/ManagedFrameworks/Python.framework/Versions/Current/bin/python3
"""
###################################################################################################
# Script Name:  AppBlocker.py
# By:  Zack Thompson / Created:  9/21/2019
# Version:  1.2.0 / Updated:  11/10/2022 / By:  ZT
#
# Description:  This scripts creates a framework that allows the blocking of apps based on their bundle
#               identifiers and pushing the "block list" via a custom configuration profile.
#
# Credit:  Fork of Erik Berglund's AppBlocker (https://github.com/erikberglund/AppBlocker).
#
###################################################################################################
"""

import argparse
import Foundation
import importlib
import logging
import os
import platform
import plistlib
import re
import shlex
import shutil
import signal
import subprocess
import sys

from AppKit import (
    CFPreferencesCopyAppValue, NSAlert, NSApp,
    NSImage, NSInformationalAlertStyle, NSObject
)
from PyObjCTools import AppHelper


__version__ = "1.2.0"


def log_setup():
    """Setup logging"""

    # Create logger
    logger = logging.getLogger("AppBlocker")
    logger.setLevel(logging.DEBUG)
    # Create file handler which logs even debug messages
    file_handler = logging.FileHandler("/var/log/AppBlocker.log")
    file_handler.setLevel(logging.INFO)
    # Create console handler with a higher log level
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.DEBUG)
    # Create formatter and add it to the handlers
    formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    file_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)
    # Add the handlers to the logger
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)


# Initialize logging
log_setup()
logger = logging.getLogger("AppBlocker")


def execute_process(command, input=None, use_shell=False):
    """
    A helper function for subprocess.

    Args:
        command (str):  The command line level syntax that would be written in a
            shell script or a terminal window

    Returns:
        dict:  Results in a dictionary
    """

    # Validate that command is not a string
    if not isinstance(command, str):
        raise TypeError("Command must be a str type")

    if not use_shell:
        # Format the command
        command = shlex.split(command)

    # Run the command
    process = subprocess.Popen(
        command,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        shell=use_shell,
        universal_newlines=True
    )

    if input:
        (stdout, stderr) = process.communicate(input=input)

    else:
        (stdout, stderr) = process.communicate()

    return {
        "stdout": (stdout).strip(),
        "stderr": (stderr).strip() if stderr != None else None,
        "exitcode": process.returncode,
        "success": True if process.returncode == 0 else False
    }


def create_daemon(**parameters):

    logger.info("Creating the LaunchDaemon...")

    # Setup local variables for ease
    script_location = parameters.get("script_location")
    launch_daemon_location = parameters.get("launch_daemon_location")
    launch_daemon_label = parameters.get("launch_daemon_label")

    # Create LaunchDaemon configuration in a dictionary
    launch_daemon_plist = {
        "Label": launch_daemon_label,
        "ProgramArguments": [
            sys.executable,
            f"{script_location}",
            "--action",
            "run",
            "--domain",
            launch_daemon_label
        ],
        "KeepAlive": True,
        "RunAtLoad": True
    }

    # Write the LaunchDaemon configuration to disk
    plistlib.dump(launch_daemon_plist, launch_daemon_location)


def start_daemon(**parameters):
    """Check if the LaunchDaemon is running, if so restart
    it in case a change was made to the plist file."""

    # Setup local variables for ease
    launch_daemon_location = parameters.get("launch_daemon_location")
    launch_daemon_label = parameters.get("launch_daemon_label")
    os_minor_version = parameters.get("os_minor_version")

    # Determine proper launchctl syntax based on OS Version
    if os_minor_version >= 11:
        exit_code = execute_process(
            f"/bin/launchctl print system/{launch_daemon_label} > /dev/null 2>&1; echo $?"
        ).get("exitcode")

        if int(exit_code) != 0:
            logger.info("Loading LaunchDaemon...")
            execute_process(f"/bin/launchctl bootstrap system {launch_daemon_location}")

        execute_process(f"/bin/launchctl enable system/{launch_daemon_label}")

    elif os_minor_version <= 10:
        exit_code = execute_process(
            f"/bin/launchctl list {launch_daemon_label} > /dev/null 2>&1; echo $?").get("exitcode")

        if int(exit_code) != 0:
            logger.info("Loading LaunchDaemon...")
            execute_process(f"/bin/launchctl load {launch_daemon_location}")


def stop_daemon(**parameters):
    """Check if the LaunchDaemon is running and stop it if so."""

    # Setup local variables for ease
    launch_daemon_location = parameters.get("launch_daemon_location")
    launch_daemon_label = parameters.get("launch_daemon_label")
    os_minor_version = parameters.get("os_minor_version")

    # Determine proper launchctl syntax based on OS Version
    if os_minor_version >= 11:
        exit_code = execute_process(
            f"/bin/launchctl print system/{launch_daemon_label} > /dev/null 2>&1; echo $?"
        ).get("exitcode")

        if int(exit_code) == 0:
            logger.info("Stopping the LaunchDaemon...")
            execute_process(f"/bin/launchctl bootout system/{launch_daemon_label}")

    elif os_minor_version <= 10:
        exit_code = execute_process(
            f"/bin/launchctl list {launch_daemon_label} > /dev/null 2>&1; echo $?").get("exitcode")

        if int(exit_code) == 0:
            logger.info("Stopping the LaunchDaemon...")
            execute_process(f"/bin/launchctl unload {launch_daemon_label}")


class AppLaunch(NSObject):
    """Define callback for notification"""

    def __init__(self):
        super(NSObject, self).__init__()
        self.preference_domain = None

    def appLaunched_(self, notification):

        # Get all the configured Applications
        blocked_apps = list(CFPreferencesCopyAppValue("BlockedApps", self.preference_domain))

        # List of all blocked bundle identifiers. Can use Regex strings.
        blocked_bundle_identifiers = [
            blockedBundleID["Application"] for blockedBundleID in blocked_apps ]

        # Combine all bundle identifiers and Regex strings to one
        blocked_bundle_identifiers_combined = "(" + ")|(".join(blocked_bundle_identifiers) + ")"

        # Store the userInfo dict from the notification
        user_info = notification.userInfo

        # Get the launched applications bundle identifier
        bundle_identifier = user_info()["NSApplicationBundleIdentifier"]

        # Check if launched app's bundle identifier matches any 'blocked_bundle_identifiers'
        if re.match(blocked_bundle_identifiers_combined, bundle_identifier):

            app_name = user_info()["NSApplicationName"]

            for blocked_list in blocked_apps:
                if blocked_list["Application"] == bundle_identifier:
                    blocked_app = blocked_list

            console_user = (execute_process(
                "/usr/sbin/scutil <<< \'show State:/Users/ConsoleUser\' | /usr/bin/awk \'/Name :/ && ! /loginwindow/ { print $3 }\'",
                use_shell=True
            )).get("stdout")
            logger.info(
                f"Restricted application '{app_name}' matching bundleID '{bundle_identifier}' was opened by {console_user}.")

            # Get path of launched app
            path = user_info()["NSApplicationPath"]

            # Get PID of launched app
            pid = user_info()["NSApplicationProcessIdentifier"]

            # Quit launched app
            os.kill(pid, signal.SIGKILL)

            # Alert user
            if blocked_app["AlertUser"]:

                try:
                    app_icon = CFPreferencesCopyAppValue(
                        "CFBundleIconFile", f"{path}/Contents/Info.plist")
                    alert_icon_path = f"{path}/Contents/Resources/{app_icon}"
                    _, ext = os.path.splitext(alert_icon_path)

                    if not ext:
                        alert_icon_path += ".icns"

                except Exception:
                    alert_icon_path = None

                alert(
                    blocked_app["AlertTitle"].format(appname=app_name),
                    blocked_app["AlertMessage"],
                    ["OK"],
                    alert_icon_path
                )

            # Delete app if blocked
            if blocked_app["DeleteApp"]:
                try:
                    shutil.rmtree(path)
                except OSError as error:
                    print (f"Error: {error.filename} - {error.strerror}.")


class Alert(object):
    """Define alert class"""

    def __init__(self, messageText):
        super(Alert, self).__init__()
        self.messageText = messageText
        self.informativeText = ""
        self.buttons = []
        self.icon = ""

    def displayAlert(self):
        alert = NSAlert.alloc().init()
        alert.setMessageText_(self.messageText)
        alert.setInformativeText_(self.informativeText)
        alert.setAlertStyle_(NSInformationalAlertStyle)
        for button in self.buttons:
            alert.addButtonWithTitle_(button)

        if self.icon and os.path.exists(self.icon):
            icon = NSImage.alloc().initWithContentsOfFile_(self.icon)
        else:
            icon = NSImage.alloc().initWithContentsOfFile_(
                "/System/Library/CoreServices/CoreTypes.bundle/Contents/Resources/AlertStopIcon.icns")

        alert.setIcon_(icon)

        # Don't show the Python rocketship in the dock
        NSApp.setActivationPolicy_(1)

        NSApp.activateIgnoringOtherApps_(True)
        alert.runModal()


def alert(title, message, buttons, app_icon=None):
    """Create an alert

    Args:
        title (str, required): The title of the alert dialog.
        message (str, required): The message body of the alert dialog.
        buttons (list, required): Buttons to be displayed on the alert dialog.
        app_icon (str, optional): The icon to display.  Defaults to:
            "/System/Library/CoreServices/CoreTypes.bundle/Contents/Resources/AlertStopIcon.icns".
    """

    alert_app = Alert(title)
    alert_app.informativeText = message
    alert_app.buttons = buttons
    alert_app.icon = app_icon
    alert_app.displayAlert()


def main():

    logger.debug(f"All calling args:  {sys.argv}")

    ##################################################
    # Define Script Parameters

    parser = argparse.ArgumentParser(
        description="This script allows you to block applications based on bundle identifier, optionally delete the app, and notify the user.")
    parser.add_argument("--action", "-a", metavar="[ run | install | uninstall ]", type=str,
        help="Install or Uninstall the application blocking LaunchDaemon.", required=True)
    parser.add_argument("--domain", "-d", metavar="com.github.mlbz521.BlockedApps", type=str,
        help="The preference domain of the block list.  Also used for the launchdaemon name.",
        required=True)

    args = parser.parse_known_args()
    args = args[0]
    logger.debug(f"Argparse args:  {args}")

    if len(sys.argv) > 1:
        if args.domain:
            preference_domain = (args.domain).strip()
        if args.action:
            action = (args.action).strip()
    else:
        parser.print_help()
        sys.exit(0)

    ##################################################
    # Define Variables

    os_minor_version = int(platform.mac_ver()[0].split(".")[1])
    launch_daemon_label = preference_domain
    launch_daemon_location = f"/Library/LaunchDaemons/{launch_daemon_label}.plist"
    script_location = "/usr/local/bin/AppBlocker"

    ##################################################

    if action == "install":
        logger.info("Installing the AppBlocker service...")

        if os.path.exists(script_location):
            logger.info("Service already exists; checking version...")
            dirname, basename = os.path.split(script_location)
            sys.path.insert(1, dirname)
            system_name = os.path.splitext(basename)[0]
            system_instance = importlib.import_module(system_name)
            system_version = system_instance.__version__

            if system_version == __version__:
                logger.info("Version:  current")

            else:
                logger.info("Updating the systems' AppBlocker service...")
                # "Install" script
                shutil.copy(__file__, script_location)

                # Create the LaunchDaemon
                create_daemon(
                    script_location=script_location,
                    launch_daemon_label=launch_daemon_label,
                    launch_daemon_location=launch_daemon_location
                )
                stop_daemon(
                    launch_daemon_label=launch_daemon_label, os_minor_version=os_minor_version)

        else:
            # "Install" script
            shutil.copy(__file__, script_location)

            # Create the LaunchDaemon
            create_daemon(
                script_location=script_location,
                launch_daemon_label=launch_daemon_label,
                launch_daemon_location=launch_daemon_location
            )
            stop_daemon(launch_daemon_label=launch_daemon_label, os_minor_version=os_minor_version)

        start_daemon(
            launch_daemon_label=launch_daemon_label,
            launch_daemon_location=launch_daemon_location,
            os_minor_version=os_minor_version
        )

    elif action == "uninstall":
        logger.info("Removing the AppBlocker service...")

        if os.path.exists(script_location):
            try:
                os.remove(script_location)
            except OSError as error:
                logger.error(f"Error: {error.filename} - {error.strerror}.")

        # Stop the LaunchDaemon
        stop_daemon(launch_daemon_label=launch_daemon_label, os_minor_version=os_minor_version)

        if os.path.exists(launch_daemon_location):
            os.remove(launch_daemon_location)

    elif action == "run":
        # Register for 'NSWorkspaceDidLaunchApplicationNotification' notifications
        notification_center = Foundation.NSWorkspace.sharedWorkspace().notificationCenter()
        app_blocker = AppLaunch.new()
        app_blocker.preference_domain = preference_domain
        notification_center.addObserver_selector_name_object_(
            app_blocker, "appLaunched:", "NSWorkspaceWillLaunchApplicationNotification", None)

        logger.info("Starting AppBlocker...")
        # Launch "app"
        AppHelper.runConsoleEventLoop()
        logger.info("Stopping AppBlocker...")


if __name__ == "__main__":
    main()
