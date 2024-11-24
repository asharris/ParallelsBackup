# Parallels Backup

#### Introduction   
backupParallels.py is a Python3 script to make complete backups of Virtual Machines (VM) running under Parallels. Tar is used to create a single file of all the files in the VM and the file is then compressed before being copied to the destination.

Before a backup is started, any running VMs are suspended. The cumulative runtime for the VM is checked and if it is greater than the cumulative runtime the last time the VM was backed up a backup is made. If the VM was running, it is resumed after a copy is taken.

Optional commands can be run before a VM is suspended or after it is resumed.

A configuration file contains various information needed by the backup, including what compression to use, the destination for the backups and how many backups should be stored before they are overwritten.

Command can be run before the whole process starts as well as when the whole process has completed.

#### Backup Process   
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

#### The configuration file   
The configuration file can be one of:   
* ~/.backupParallels.ini   
* /etc/backupParallels.ini   

The first file found is used. If neither file is found, the program exists with an error. If both files are found, then ~/.backupParallels.ini is used.



