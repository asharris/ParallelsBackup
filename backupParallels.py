#!/usr/bin/env python3

import os, sys, subprocess, time, datetime, argparse, re
import signal
import sys
from threading import Thread
import threading
from pathlib import Path
import configparser


# Where the backups are stored
scpDestinations = []
# Where the last backup information is stored
cdir = ""
# Compression Information
compressProgram = ""
compressExtension = ""
compressArgs = []
# Number of backs to retain
backupRotations = 3 # This is set in the config file

# The Parallels Control Program
prlctl = ''
tar = ''

errorCount = 0
wasRunning = []
backupList = ''
nBackups = int(0)

parser = argparse.ArgumentParser(description = 'Backup Parallels VMs')
parser.add_argument('-o', '--output', default = '', help = 'Append output to a file')
args = parser.parse_args()

def plog(txt):
  dt = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
  if args.output != '':
    with open(args.output, 'a') as fp:
      print(f"{dt}: {txt}", file=fp, )
  else:
    print(f"{dt}: {txt}", flush=True)
  
"""
  run(params):
      params: a list of program parameters, can be a simple string or an array
              if a string is passed, it is converted to an array
      returns: a tuple of [exit value, stdout, stderr]

"""
def run(params, systimeout = 30):
  global errorCount

  if type(params) is str:
    # Split the string on words
    params = params.split()
  try:
    with subprocess.Popen(params, stdout=subprocess.PIPE, stderr=subprocess.PIPE) as p:
      try:
        std, ste = p.communicate(timeout = systimeout);
      except subprocess.TimeoutExpired:
        p.kill()
        std = ''
        return [255, std, 'Command timeout']
      except Exception as e:
        return [254, '', f"Exception {e}"]
  except Exception as e:
    return [253, '', f"Exception {e}"]
  return [p.returncode, std.decode(), ste.decode()]

"""
  resume:
      If a VM is in the suspended state, then resume it.
      If a section exists in the config file with this VM name then execute it's parts
"""
def resume(vm):
  global errorCount

  out = run([prlctl, 'list',  '-i',  '-ostatus,id,name', vm])
  if out[0] != 0:
    plog(f"Failed to resume {vm}: {out[2]}")
    errorCount += 1
    return
  lines = out[1].strip().split("\n")
  for line in lines:
    if line.startswith('State'):
      s = line.split()
      if s[1] == "suspended":
        plog(f"Resuming {vm}")
        run([prlctl, 'resume', vm])
        # Run any "After Resume" commands for this VM
        runSection(vm, 'AfterResume')

"""
  suspend:
      Suspend a VM only if it is running
      Also run any pre-suspend commands
"""       
def suspend(vm):
  global errorCount
  
  out = run([prlctl, 'list',  '-i',  '-ostatus,id,name', vm])
  if out[0] != 0:
    plog(f"Failed to get state of {vm}: {out[2]}")
    errorCount += 1
    lines = []
  lines = out[1].strip().split("\n")
  for line in lines:
    if line.startswith('State'):
      s = line.split()
      if s[1] == "running":
        # Run any "Before Suspend" commands for this VM
        runSection(vm, 'BeforeSuspend')
        plog(f"Suspending {vm}")
        run([prlctl, 'suspend', vm])
        wasRunning.append(vm)


def runSection(sectionHeading, sectionName):
  sections = config.sections()
  if sectionHeading in sections:
    section = config[sectionHeading]
    allCmds = section.get(sectionName, '').split("\n")
    for cmd in allCmds:
      cmd = cmd.strip()       # Remove leading or trailing space
      if cmd == '':
        continue
      if cmd.startswith('+'): # Just print the line - don't run it
        cmd = cmd[1:]
        plog(cmd)
        continue
      if cmd.startswith('-'): # Leading '-' means do not echo it
        cmd = cmd[1:]
      else:
        plog(cmd)
      os.system(cmd)


"""
    copyByScp:
          Copies the file to the destination
"""
def copyByScp(frm, to):
  global errorCount, scpTimeout

  plog(f'scp {frm} {to}')
  out = run(['scp', frm, to], systimeout=scpTimeout)
  if out[0] != 0:
    plog(f"scp to {to} failed: {out[2]}")
    errorCount +=1
  else:
    plog(f"scp completed to {to} ")

"""
  extractValue:
          To ensure efficiency, each VMs details are read only once, and stored
          in the allVms dictionary
          For the particular VM the required value is returned. 
"""
def extractValue(vm, value):
  global errorCount
  
  # Initialise local storage of allVms
  try:
    x = extractValue.allVms
  except AttributeError:
    extractValue.allVms = {}

  # Cache VM if not yet there
  if not vm in extractValue.allVms:
    out = run([prlctl, 'list', '-i', vm])
    if out[0] != 0:
      plog(f"Error getting details values from {vm}: {out[2]}")
      errorCount += 1
      return ''
    else:
      lines = out[1].strip().split("\n")
      extractValue.allVms[vm] = lines
  else:
    lines = extractValue.allVms[vm]
  for line in lines:
    line = ' '.join(line.split())
    s = line.split(':', 1)
    if s[0] == value:
      return s[1].strip()
  return ''

"""
  uptimeToSecs:
          The uptime is a string which may include days as well as time.
          This returns the total time in seconds.
"""
def uptimeToSecs(uptime):
  # Two regular expressions used to extract the total uptime from the VMs information
  re1 = r"(\d*)\s*days\s*(\d{2}):(\d{2}):(\d{2})\s"
  re2 = r"(\d{2}):(\d{2}):(\d{2})\s"
  matches = re.search(re1, uptime)
  if matches:
    days = int(matches.group(1))
    hours = int(matches.group(2))
    minutes = int(matches.group(3))
    seconds = int(matches.group(4))
  else:
    matches = re.search(re2, uptime)
    if matches:
      days = 0
      hours = int(matches.group(1))
      minutes = int(matches.group(2))
      seconds = int(matches.group(3))
  tseconds = (((days * 24 + hours) * 60) + minutes) * 60 + seconds;
  return tseconds

"""
  return 's' if n does not equal 1
"""
def s(n):
  n = int(n)
  return '' if n == 1 else 's'

"""
  doBackup:
            This performs the following:
              1: Tar
              2: Resume VM (if it was running)
              3: Compression
              4: Scp
            The reason the tar and the compression are separated is that tar on it's own is
            much faster; that way we can minimise the time the VM is suspended.
            Each of the scps are done concurrently, as the limiting factor is most
            likely to be the destination writing.
"""
def doBackup(vm, sourceLocation, backupNumber, originalState):
  global backupList, nBackups, errorCount, scpTimeout, nCopies

  # Do a tar, without compression as we can do this a lot faster
  # and that means we can resume a suspended VM much more quickly
  tarFile = f"/private/tmp/{vm}.tar"
  # Remove the leading "/" so tar doesn't have to (and issue a warning)
  source = sourceLocation.lstrip('/')
  out = run([tar, "cf", tarFile, source], systimeout = 1200)
  if out[0] != 0:
    plog(f"Error of tar of {tarFile}: {out[2]}")
    errorCount +=1
  if originalState == 'running':
    resume(vm)
  # Compress the tar file
  sizeOrg = os.path.getsize(tarFile)
  plog(f"Compressing {tarFile} using {compressProgram}")
  out = run([compressProgram] + compressArgs + [tarFile], compressTimeout) 
  if out[0] != 0:
    plog(f"Error during compression of {tarFile} : {out[2]}")
    errorCount +=1
    return
  sizeComp = os.path.getsize(f"{tarFile}.{compressExtension}") 
  plog(f"Compressed from {sizeOrg/(1024 * 1024 * 1024):.2f}Gb to {sizeComp / (1024 * 1024 * 1024):.2f}Gb: "
        f"{(sizeComp * 100 / sizeOrg):.2f}%")
  # Now run all the scp's concurrently
  threads = list()
  for dest in scpDestinations:
    x = threading.Thread(target=copyByScp, args=(f"{tarFile}.{compressExtension}", f"{dest}/{vm}.{backupNumber}.tar.{compressExtension}"))
    threads.append(x)
    x.start()
  # Wait until they have all finished
  for index, thread in enumerate(threads):
    thread.join(scpTimeout)
  # Remove the temp file
  os.unlink(f"{tarFile}.{compressExtension}") 
  nCopies = len(scpDestinations)
  plog(f"{nCopies} copies of {vm} completed")
  backupList = backupList + f"{vm}[{backupNumber}] "
  nBackups += 1
  nBackups = int(nBackups)

def getSettings():
  global scpDestinations, cdir, compressProgram, compressExtension, compressTimeout, scpTimeout
  global compressArgs, backupRotations, prlctl, tar, config

  configFiles = [os.path.expanduser('~/') + '.backupParallels.ini', '/etc/backupParallels.ini']
  for fname in configFiles:
    if os.path.exists(fname):
      config = configparser.ConfigParser()
      try:
        config.read(fname)
      except Exception as e:
        plog(f"Error reading from configuration file: {fname}: {e}")
        exit(1)
      break
  if config == None:
    plog(f"Error: Configuration {configFiles} not found")
    exit(1)

  try:
    prlctl = config['main'].get('prlctl', '/usr/local/bin/prlctl')
    tar = config['main'].get('tar', '/usr/bin/tar')
    # Setup the scpDestinations
    scp = config['scp']
    scpDestinations = scp.get('destinations', '').split("\n")
    scpTimeout = int(scp.get('timeout', '7200'))
    # Setup the compression program
    compression = config['compression']
    compressProgram = compression.get('program', '/usr/bin/gzip')
    compressExtension = compression.get('compressedExtension', 'gz')
    compressArgs = compression.get('arguments', '-f').split()
    compressTimeout = int(compression.get('timeout', '3600'))

    # Setup the Status Directory
    cdir = config['main']['StatusDirectory']
    # Backup Rotaions
    backupRotations = int(config['main'].get('backupRotations', 3))
  except Exception as e:
    plog(f"Error reading from the configuration: {configFiles}: {e}")
    exit(1)
  return config


# Main Logic
os.chdir("/")
msg = f"BackupParallels.py Started at {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
plog(f"{'=' * len(msg)}")
plog(f"{msg}")
config = getSettings()
runSection('main','BeforeBackup')
# Get a list of VMs
out = run([prlctl, 'list', '-a'])
if out[0] != 0:
  plog(f"Error running prlctl: {out[2]}")
  exit(1)
lines = out[1].strip().split("\n")
for line in lines:
  # Don't read from the headings or empty lines
  if not line.endswith('NAME'):
    line = ' '.join(line.split())
    s = line.split(' ', 3) # The VM Name is the last entry and can have spaces in it. This ensures the VM Name is one field
    if len(s) > 3:
      #Fields are: 0: VM id, 1: Status, 2: The '-' char, 3: VM Name
      vm = s[3]
      originalState = s[1]
      plog(f"{vm}")
      plog("-" * len(vm))
      if originalState == 'running':
        suspend(vm)
      # Get the location for the VM
      sourceLocation = extractValue(vm, "Home")
      uptime = uptimeToSecs(extractValue(vm, "Uptime"))
      # Read from the appropriate cdir file
      cdirFile = f"{cdir}/{vm}.last"
      lastBackupNumber = 0
      lastUptime = 0
      try:
        f = open(cdirFile, 'r')
        s = f.readline().split()
        f.close()
        if len(s) > 1:
          lastBackupNumber = int(s[0])
          lastUptime = int(s[1])
      except Exception as e:
        plog(f"{cdirFile} not found or not readable - forcing a backup")
      if uptime < 1:
        uptime = 1
      elif uptime < lastUptime: # This should not happen, but is probably because the VM has been moved.
        lastUptime = 0          # So invalidate the lastUptime to force a backup
      plog(f"{vm}: Up: {uptime}, lastUp: {lastUptime}, Location: {sourceLocation}, lastBackup no: {lastBackupNumber}")
      if uptime > lastUptime:
        plog(f"Backuping up {vm}")
        # We must do the backup
        backupNumber = lastBackupNumber + 1
        if backupNumber > backupRotations:
          backupNumber = 0
        doBackup(vm, sourceLocation, backupNumber, originalState)
        # update the cdir file with the backup number and the total uptime
        try:
          f = open(cdirFile, 'w')
          f.writelines([f"{backupNumber} {uptime}\n"])
          f.close()
        except Exception as e:
          plog(f"Error writing to {cdirFile}")
      else:
        plog(f"Not backing up {vm}")
runSection('main','AfterBackup')
nBackups = int(nBackups)
plog(f"Completed {nBackups} backup{'' if nBackups == 1 else 's'} "
     f"to {nCopies} destination{'' if nCopies == 1 else 's'} "
     f"with {errorCount} error{'' if errorCount == 1 else 's'} : {backupList}")
