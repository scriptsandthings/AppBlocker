AppBlocker
======
This is an all-in-one framework that will allow you to block applications by specifying the Bundle ID of the application and provide a custom notification message for the app along with additional functionality.

_Because the blocking is done by the bundle identifier, the location or name of the application bundle doesn't matter._


## About
This is customized fork of Erik Berglund's [AppBlocker](https://github.com/erikberglund/AppBlocker).  While the base functionality is very similar, the features and delivery method have been tweaked.

Essentially, you deploy a custom managed preference domain (aka a custom plist file) to your Macs listing the applications to block and other configurable bits.  Then "install" the script which reads the managed preference domain.  This allows you to customize your blocked application list on the fly via Apple Push Notifications.

I would recommend configuring the deployment of the Configuration Profile first and then "trigger" the install of the script once the Config Profile has been installed.

All blocked launches are recorded in a log file found here:  `/var/log/AppBlocker.log`


## Notification
The **Title** and **Message** text are completely customizable and the icon will be pulled from the application bundle when it is launched; if an icon cannot be found, a default one will be used.

<center><img src="https://github.com/mlbz521/AppBlocker/blob/master/Example Files/Sample Notification.png" width="50%" height="50%" /></center>

## How to setup
You'll need to create a plist file with a BlockedApps key with an array of dictionaries.  Details for each dictionary key:

  * Application
    * The Bundle Identifier for each application
    * To get the bundle identifier for an app, run the following command:
      * `defaults read "/Applications/Install macOS Mojave.app/Contents/Info.plist" CFBundleIdentifier`
  * DeleteApp
    * True
    * False
  * AlertUser
    * Prompt the user with a notification
      * True
      * False
  * AlertTitle
    * The top, bolded caption in the notification
  * AlertMessage
    * The lower caption in the notification

The variable `{appname}` can be used to enter the name of the App that is being blocked within the notification.  Save as a plain text document with a name in the format of a reverse domain name, example:  `com.github.mlbz521.BlockedApps.plist`


### Example plist file:

```
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
	<key>BlockedApps</key>
	<array>
		<dict>
			<key>Application</key>
			<string>com.apple.InstallAssistant.Catalina</string>
			<key>DeleteApp</key>
			<false />
			<key>AlertUser</key>
			<true />
			<key>AlertTitle</key>
			<string>macOS Catalina is not yet supported.</string>
			<key>AlertMessage</key>
			<string>Please contact IT Support for more information and to verify that your current applications will support macOS Catalina.</string>
		</dict>
		<dict>
			<key>Application</key>
			<string>com.apple.Chess</string>
			<key>DeleteApp</key>
			<false />
			<key>AlertUser</key>
			<true />
			<key>AlertTitle</key>
			<string>The application "{appname}" has been blocked.</string>
			<key>AlertMessage</key>
			<string>This app is not allowed.  Contact IT Support for more information.</string>
		</dict>
	</array>
</dict>
</plist>
```


## Create Monitoring Service

Run the `AppBlocker.py` script to "install" the service; it will create a launchdaemon and a copy of the `AppBlocker.py` script on the local device here:  `/usr/local/bin/AppBlocker`.

```
$ sudo python AppBlocker.py --help

usage: AppBlocker.py [-h] --action [run | install | uninstall] --domain
                     com.github.mlbz521.BlockedApps

This script allows you to block applications based on bundle identifier,
optionally delete the app, and notify the user.

arguments:
  -h, --help            show this help message and exit
  --action [ run | install | uninstall ], -a [ run | install | uninstall ]
                        Install or Uninstall the application blocking
                        LaunchDaemon.
  --domain com.github.mlbz521.BlockedApps, -d com.github.mlbz521.BlockedApps
                        The preference domain of the block list. This will
                        also be used for the launchdaemon.
```

*Must be ran with `sudo`, it's only needed because of the location of the log file.*


## Logic behind Script and Service
When the `install` parameter is passed to the script to install the service, it checks if the service for the managed preference domain already exists, if it does, it checks if the "local copy" of the scripts' version is up to date, if it is out of date, it will update itself.

When the `run` parameter is passed to the script, it monitors when apps are opened and checks them against the block list in the managed preference domain.  If the CFBundleIdentifier matches, it immediately kills the application.


## Disclaimer
For true blacklisting of binary execution, look at Google's Santa project: https://github.com/google/santa

This script doesn't literally "block" the execution of an application, it gets notified when an application is being launched and sends a `SIGKILL` signal to the process.

It's a simple method to help administrators stop their users from using applications the organization has decided should not be allowed. If you have a management framework with a similar feature, you should use that instead.
