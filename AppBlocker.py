#!/opt/ManagedFrameworks/Python.framework/Versions/Current/bin/python3
"""
###################################################################################################
# Script Name:  AppBlocker.py
# By:  Zack Thompson / Created:  9/21/2019
# Version:  1.1.1 / Updated:  11/7/2022 / By:  ZT
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
import shutil
import signal
import subprocess
import sys

from AppKit import *
from PyObjCTools import AppHelper


__version__ = "1.1.0"


def runUtility(command):
    """A helper function for subprocess.
    Args:
        command:  String containing the commands and arguments that will be passed to a shell.
    Returns:
        stdout:  output of the command
    """

    # Setup logging
    logger = logging.getLogger('AppBlocker')

    try:
        process = subprocess.check_output(command, shell=True)
    except subprocess.CalledProcessError as error:
        logger.error('Error code:  {}'.format(error.returncode))
        logger.error('Error:  {}'.format(error))
        process = error

    return process


# Setup logging
def log_setup():
    # Create logger
    logger = logging.getLogger('AppBlocker')
    logger.setLevel(logging.DEBUG)
    # Create file handler which logs even debug messages
    file_handler = logging.FileHandler('/var/log/AppBlocker.log')
    file_handler.setLevel(logging.INFO)
    # Create console handler with a higher log level
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.DEBUG)
    # Create formatter and add it to the handlers
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    file_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)
    # Add the handlers to the logger
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)


def createDaemon(**parameters):
    # Setup logging
    logger = logging.getLogger('AppBlocker')
    logger.info('Creating the LaunchDaemon...')

    # Setup local variables for ease
    script_location = parameters.get('script_location')
    launch_daemon_location = parameters.get('launch_daemon_location')
    launch_daemon_label = parameters.get('launch_daemon_label')

    # Create LaunchDaemon configuration in a dictionary
    launch_daemon_plist = {
    "Label" : launch_daemon_label,
    'ProgramArguments' : ["/usr/bin/python", "{}".format(script_location), '--action', 'run', '--domain', launch_daemon_label],
    'KeepAlive' : True,
    'RunAtLoad' : True
    }
    
    # Write the LaunchDaemon configuration to disk
    plistlib.dump(launch_daemon_plist, launch_daemon_location)


# Check if the LaunchDaemon is running, if so restart it in case a change was made to the plist file.
def startDaemon(**parameters):
    # Setup logging
    logger = logging.getLogger('AppBlocker')

    # Setup local variables for ease
    launch_daemon_location = parameters.get('launch_daemon_location')
    launch_daemon_label = parameters.get('launch_daemon_label')
    os_minor_version = parameters.get('os_minor_version')

    # Determine proper launchctl syntax based on OS Version
    if os_minor_version >= 11:
        launchctl_print = '/bin/launchctl print system/{} > /dev/null 2>&1; echo $?'.format(launch_daemon_label)
        exitCode = runUtility(launchctl_print)

        if not int(exitCode) == 0:
            logger.info('Loading LaunchDaemon...')
            launchctl_bootstrap = '/bin/launchctl bootstrap system {}'.format(launch_daemon_location)
            runUtility(launchctl_bootstrap)

        launchctl_enable = '/bin/launchctl enable system/{}'.format(launch_daemon_label)
        runUtility(launchctl_enable)

    elif os_minor_version <= 10:
        launchctl_list = '/bin/launchctl list {} > /dev/null 2>&1; echo $?'.format(launch_daemon_label)
        exitCode = runUtility(launchctl_list)

        if int(exitCode) != 0:
            logger.info('Loading LaunchDaemon...')
            launchctl_enable = '/bin/launchctl load {}'.format(launch_daemon_location)
            runUtility(launchctl_enable)


# Check if the LaunchDaemon is running and stop it if so.
def stopDaemon(**parameters):
    # Setup logging
    logger = logging.getLogger('AppBlocker')

    # Setup local variables for ease
    launch_daemon_location = parameters.get('launch_daemon_location')
    launch_daemon_label = parameters.get('launch_daemon_label')
    os_minor_version = parameters.get('os_minor_version')

    # Determine proper launchctl syntax based on OS Version
    if os_minor_version >= 11:
        launchctl_print = '/bin/launchctl print system/{} > /dev/null 2>&1; echo $?'.format(launch_daemon_label)
        exitCode = runUtility(launchctl_print)

        if int(exitCode) == 0:
            logger.info('Stopping the LaunchDaemon...')
            launchctl_bootout = '/bin/launchctl bootout system/{}'.format(launch_daemon_label)
            runUtility(launchctl_bootout)

    elif os_minor_version <= 10:
        launchctl_list = '/bin/launchctl list {} > /dev/null 2>&1; echo $?'.format(launch_daemon_label)
        exitCode = runUtility(launchctl_list)

        if int(exitCode) == 0:
            logger.info('Stopping the LaunchDaemon...')
            launchctl_unload = '/bin/launchctl unload {}'.format(launch_daemon_label)
            runUtility(launchctl_unload)


def main():

    ##################################################
    # Setup logging
    log_setup()
    logger = logging.getLogger('AppBlocker')
    logger.debug('All calling args:  {}'.format(sys.argv))

    ##################################################
    # Define Script Parameters

    parser = argparse.ArgumentParser(description="This script allows you to block applications based on bundle identifier, optionally delete the app, and notify the user.")
    parser.add_argument('--action', '-a', metavar='[ run | install | uninstall ]', type=str, help='Install or Uninstall the application blocking LaunchDaemon.', required=True)
    parser.add_argument('--domain', '-d', metavar='com.github.mlbz521.BlockedApps', type=str, help='The preference domain of the block list.  This will also be used for the launchdaemon.', required=True)

    args = parser.parse_known_args()
    args = args[0]   
    logger.debug('Argparse args:  {}'.format(args))

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

    os_minor_version = int(platform.mac_ver()[0].split('.')[1])
    launch_daemon_label = preference_domain
    launch_daemon_location = '/Library/LaunchDaemons/{}.plist'.format(launch_daemon_label)
    script_location = '/usr/local/bin/AppBlocker'
    console_user = (runUtility('/usr/sbin/scutil <<< "show State:/Users/ConsoleUser" | /usr/bin/awk \'/Name :/ && ! /loginwindow/ { print $3 }\'')).strip()

    ##################################################
    # Define callback for notification
    class AppLaunch(NSObject):
        def appLaunched_(self, notification):

            # Store the userInfo dict from the notification
            userInfo = notification.userInfo

            blockedApplications = []
            blockedBundleIdentifiers = []

            for dictItem in CFPreferencesCopyAppValue('BlockedApps', preference_domain):
                blockedApplications.append(dictItem)

            # List of all blocked bundle identifiers. Can use regexes.
            for blockedBundleID in blockedApplications:
                blockedBundleIdentifiers.append(blockedBundleID['Application'])

            # Combine all bundle identifiers and regexes to one
            blockedBundleIdentifiersCombined = "(" + ")|(".join(blockedBundleIdentifiers) + ")"
            
            # Get the launched applications bundle identifier
            bundleIdentifier = userInfo()['NSApplicationBundleIdentifier']

            # Check if launched app's bundle identifier matches any 'blockedBundleIdentifiers'
            if re.match(blockedBundleIdentifiersCombined, bundleIdentifier):

                app_name = userInfo()['NSApplicationName']

                for blockedList in blockedApplications:
                    if blockedList['Application'] == bundleIdentifier:
                        blockedApp = blockedList
                        
                logger.info('Restricted application \'{appname}\' matching bundleID \'{bundleID}\' was opened by {user}.'.format(appname=app_name, bundleID=bundleIdentifier, user=console_user))
                
                # Get path of launched app
                path = userInfo()['NSApplicationPath']

                # Get PID of launched app
                pid = userInfo()['NSApplicationProcessIdentifier']

                # Quit launched app
                os.kill(pid, signal.SIGKILL)

                # Alert user
                if blockedApp['AlertUser']:
                    app_icon = CFPreferencesCopyAppValue('CFBundleIconFile', '{}/Contents/Info.plist'.format(path))
                    alertIconPath = "{path}/Contents/Resources/{app_icon}".format(path=path, app_icon=app_icon)
                    root, ext = os.path.splitext(alertIconPath)
                    if not ext:
                        alertIconPath = alertIconPath + '.icns'
                    alert(blockedApp['AlertTitle'].format(appname=app_name), blockedApp['AlertMessage'], ["OK"], alertIconPath)

                # Delete app if blocked
                if blockedApp['DeleteApp']:
                    try:
                        shutil.rmtree(path)
                    except OSError as error:
                        print ("Error: {} - {}.".format(error.filename, error.strerror))

    ##################################################
    # Define alert class
    class Alert(object):

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

            if os.path.exists(self.icon):
                icon = NSImage.alloc().initWithContentsOfFile_(self.icon)
                alert.setIcon_(icon)
            else:
                icon = NSImage.alloc().initWithContentsOfFile_("/System/Library/CoreServices/CoreTypes.bundle/Contents/Resources/AlertStopIcon.icns")
                alert.setIcon_(icon)

            # Don't show the Python rocketship in the dock
            NSApp.setActivationPolicy_(1)

            NSApp.activateIgnoringOtherApps_(True)
            alert.runModal()

    ##################################################
    # Define an alert
    def alert(message="Default Message", info_text="", buttons=["OK"], app_icon=""):	   
        ap = Alert(message)
        ap.informativeText = info_text
        ap.buttons = buttons
        ap.icon = app_icon
        ap.displayAlert()

    ##################################################

    if action == 'install':
        logger.info('Installing the AppBlocker service...')

        if os.path.exists(script_location):
            logger.info('Service already exists; checking version...')
            dirname, basename = os.path.split(script_location)
            sys.path.insert(1, dirname)
            system_name = os.path.splitext(basename)[0]
            system_instance = importlib.import_module(system_name)
            system_version = system_instance.__version__

            if system_version == __version__:
                logger.info('Version:  current')
                startDaemon(launch_daemon_label=launch_daemon_label, launch_daemon_location=launch_daemon_location, os_minor_version=os_minor_version)
                
            else:
                logger.info('Updating the systems\' AppBlocker service...')
                # "Install" script
                shutil.copy(__file__, script_location)

                # Create the LaunchDaemon
                createDaemon(script_location=script_location, launch_daemon_label=launch_daemon_label, launch_daemon_location=launch_daemon_location)
                stopDaemon(launch_daemon_label=launch_daemon_label, os_minor_version=os_minor_version)
                startDaemon(launch_daemon_label=launch_daemon_label, launch_daemon_location=launch_daemon_location, os_minor_version=os_minor_version)

        else:
            # "Install" script
            shutil.copy(__file__, script_location)

            # Create the LaunchDaemon
            createDaemon(script_location=script_location, launch_daemon_label=launch_daemon_label, launch_daemon_location=launch_daemon_location)
            stopDaemon(launch_daemon_label=launch_daemon_label, os_minor_version=os_minor_version)
            startDaemon(launch_daemon_label=launch_daemon_label, launch_daemon_location=launch_daemon_location, os_minor_version=os_minor_version)

    elif action == 'uninstall':
        logger.info('Removing the AppBlocker service...')

        if os.path.exists(script_location):
            try:
                os.remove(script_location)
            except OSError as error:
                logging.ERROR("Error: {} - {}.".format(error.filename, error.strerror))

        # Stop the LaunchDaemon
        stopDaemon(launch_daemon_label=launch_daemon_label, os_minor_version=os_minor_version)

        if os.path.exists(launch_daemon_location):
            os.remove(launch_daemon_location)

    elif action == 'run':
        # Register for 'NSWorkspaceDidLaunchApplicationNotification' notifications
        nc = Foundation.NSWorkspace.sharedWorkspace().notificationCenter()
        AppLaunch = AppLaunch.new()
        nc.addObserver_selector_name_object_(AppLaunch, 'appLaunched:', 'NSWorkspaceWillLaunchApplicationNotification',None)

        logger.info('Starting AppBlocker...')
        # Launch "app"
        AppHelper.runConsoleEventLoop()
        logger.info('Stopping AppBlocker...')


if __name__ == "__main__":
    main()
