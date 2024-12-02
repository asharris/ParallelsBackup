# Parallels Backup

## Introduction   
backupParallels.py is a Python3 script to make complete backups of Virtual Machines (VM) running under Parallels. Tar is used to create a single file (tarball) of all the files in the VM and the file is then compressed before being copied to the destination.

Before a backup is started, any running VMs are suspended. The cumulative runtime for the VM is checked and if it is greater than the cumulative runtime the last time the VM was backed up, a backup is made. If the VM was running, it is resumed after a copy is taken.

Optional commands can be run before a VM is suspended or after it is resumed.

A configuration file contains information needed by the backup, including what compression to use, the destination for the backups and how many backups should be stored before they are overwritten.

Commands can be run before the whole process starts as well as when the whole process has completed.

## Synopsis
```
usage: backupParallels.py [-h] [-o OUTPUT]

Backup Parallels VMs

options:
  -h, --help            show this help message and exit
  -o OUTPUT, --output OUTPUT
                        Append output to a file
```
If an output (--output) is not specified, the output is to stdout.


## Backup Process   
1. _prlctl_ is used to get a list of VMs which are processed in order.   
2. The status of the VM is checked
  a. If running, any pre-backup commands for the VM are run
  b. The VM is suspended
3. The cumulative uptime for the VM is retrieved using _prlctl_
4. If the cumulative runtime is less than or equal to the last time the backup was run, the backup is skipped.
5. Tar is used to make a tarball of the VM
6. The VM is resumed if it had been suspended and any post resume commands are run.
7. The tarball is compressed using the utility specified in the .ini file
8. _SCP_ is used to copy the compressed tarball to the destination, or destinations. If more than one destination is specified, the scp copies are run concurrently

**N.B.** By using tar on the suspended VM without compression is very much faster than creating a tarball with compression. This is done to minimise the amount of time a VM is held in the suspended state. 

## The configuration file   
The configuration file can be one of:   
* ~/.backupParallels.ini   
* /etc/backupParallels.ini   

and must be readable by the program itself.

The first file found is used. If neither file is found, the program exits with an error. If both files exist, then ~/.backupParallels.ini is used.

The configuration file is split into several sections:
* main
* scp
* compression
* VM Name (the name of a VM as returned by ```prlctl list -a```). There can be one of these for each of the VMs on the host.

### main
1. **StatusDirectory** The status directory is the location where _.last_ files are created and updated. The director must exist before the backup program is run and have read/write permission. The status file contains the last backup number and the cumulative uptime at the time of the last backup If the file does not exist then a backup is forced and the file is created.  
2. **prlctl** This is the full path to the Parallels program '_prlctl_'. This program is used to get the names of the VBMs, the status of the VM, the location of the VM files and the cumulative uptime.  
3. **tar** The full path name of the tar program used to create the tarball.  
4. **backupRotations** If not set this defaults to '3'. Backups are named by the compressed tarball inclusive of the backup number.  
5. **BeforeBackup** Any commands to run before any backups are made. This is run once when the BackupParallels program starts  
6. **AfterBackup** Any commands to run before BackupParallels finishes.  

## scp
1. **destinations** A list of destinations normally in the format ```<user>@<destination>:<destination folder>```. Multiple destinations can be entered one line at a time (subsequent lines should be indented and the configuration reader will add all of them). If multiple destinations are entered, they will be run simultaneously. The next stage in the backup will not be run until all destination copies have been completed.  

## compression
Choosing the best compression program to use will most likely be a trade-off between the compression ratio and the time taken to compress. If multi cores can be given over to compression, programs like xz and pbzip2 can take advantage of the cores available and can be much faster.   
Choosing the optimal program will probably require some experimentation. If the compression takes too long, the backup can take a very long time. The compression ratio is important if the destination for the backups is space limited, and if the backups are being made over a slow network (perhaps to an off-site location), then getting the maximum compression is probably an important factor to take into account. The example configuration file provides multiple compression options. These options are set as follows:   

**program** The full pathname to the compression program to use    
**compressedExtension** The postfix the the compression program uses to signify compressed files   
**arguments** Any arguments to pass to the compression program. These can signify forcing overwrite of the output file or the level of compression. Several examples are shown the in example configuration file  

## VM Name (The name of the VM as given by ```prlctl list -a```)
**BeforeSuspend** Any programs to run before a VM is suspended for backup. Multiple lines can be entertd with subsequent lines indented.  
**AfterResume** Any programs to run after a VM is resumed. Multiple lines can be entered with subsequent lines indented.  

## Notes on _BeforeBackup_, _AfterBackup_, _BeforeSuspend_ and _AfterResume_.  
In each of these entries, multiple lines can be entered, with subsequent lines on the line following the first line and indented, such as:  
```
BeforeSuspend = killall Electron
        	diskutil unmount force /Volumes/<mount> &
		-sleep 5
		umount -f /Volumes/<mount> 2>/dev/null &
		-sleep 5

AfterResume =   +Mounting /Volumes/<mount>
		-osascript -e 'mount volume "smb://<user>:<password>@debian/<mount>"' &
                -sleep 5
       	        open -a 'Visual Studio Code.app' /Volumes/<mount>
		-sleep 2
```
If a lines starts with a '-' (minus sign) then the command is **not** echoed to the output. This is useful if the command contains sensitive information such as a password.

if the line starts with a '+' (addition sign), then the command is not run, but simply echoed to the output. This is useful if a command is not echoed (using a '-' due to sensitive information, but a note in the output stream is still wanted, (as in the first two lines in _AfterResume_ above.)

### Restoring a backup
Restoring a backup file requires three steps:   
1. Decompress the backup file   
2. Extract the tarball   
3. Open in Parallels Desktop   

The program used to decompress the file is dependent on the compression program used to compress the file. For instance for:   
* lz4 use ```lz4 -d```   
* gz2 or pgzip2 use ```bzip2 -d```   
* gz use  ```gunzip```  
* xz use ```xz -d```  

To extract a tarball, change directory (cd <directory name>) to where the VM is to be stored and then:  
```tar xf <decompressed filename>```   

It is also possible to do the decompression and tar extraction in a single line. i.e.:
``` gunzip < <compressed tarball> | tar x```

To open in Parallels you can simply add the new VM to the list of VMs in Parallels.
