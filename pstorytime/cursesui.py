# -*- coding: utf-8 -*-
"""A console interface based on curses. """

#
# Copyright (C) 2011 Anders Engström <ankan@ankan.eu>
#
# This file is part of pstorytime.
#
# pstorytime is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# pstorytime is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with pstorytime.  If not, see <http://www.gnu.org/licenses/>.

from threading import Thread, RLock, Event
import sys
import curses
import gobject
import glib
from datetime import timedelta
from os.path import isfile, isdir, join, expanduser, dirname, basename
import select
import signal
import os

import pygst
pygst.require("0.10")

# Don't touch my arguments!
argv = sys.argv
sys.argv = []
import gst
sys.argv = argv

import argparse
import time

from pstorytime.audiobook import AudioBook
from pstorytime.misc import PathGen, FileLock, DummyLock, LockedException, ns_to_str, parse_pos
from pstorytime.timer import Timer
import pstorytime.audiobookargs

class Select(object):
  def __init__(self,curseslock,conf,geom,audiobook,reader):
    self._lock = RLock()
    self._geom = geom
    self._window = geom.newwin()
    self._curseslock = curseslock
    self._audiobook = audiobook
    self._reader = reader

    self._audiobook.connect("notify::playlog",self._on_playlog)

    self._last_entry = None

    self._logsel = LogSelect( self._window,
                              conf,
                              self._geom,
                              self._curseslock,
                              self._audiobook)
    self._filesel = FileSelect( self._window,
                                self._geom,
                                self._curseslock,
                                self._audiobook)
    self._focus = self._logsel

    self._reader.connect("event",self._on_event)
    self.update()

  def getGeom(self):
    with self._lock:
      return self._geom

  def setGeom(self,geom):
    with self._lock:
      with self._curseslock:
        self._geom = geom
        self._logsel.setGeom(geom)
        self._filesel.setGeom(geom)
        if self._geom.is_sane():
          self._window.resize(geom.h,geom.w)
          self._window.mvwin(geom.y,geom.x)
          self.update()

  def _on_playlog(self,ab,prop):
    with self._lock:
      if self._focus == self._logsel:
        playlog = self._audiobook.playlog
        if len(playlog)>0 and playlog[-1]!=self._last_entry:
          self.update()

  def _on_event(self,obj,event):
    data = event.split()
    if len(data)>0:
      cmd = data[0]
      if cmd=="up":
        self._focus.move(-1)
        return True

      elif cmd=="down":
        self._focus.move(1)
        return True

      elif cmd=="ppage":
        self._focus.ppage()
        return True

      elif cmd=="npage":
        self._focus.npage()
        return True

      elif cmd=="begin":
        self._focus.move_to(0)
        return True

      elif cmd=="end":
        self._focus.move_to(None)
        return True

      elif cmd=="swap_view":
        self._swap_view()
        return True

      elif cmd=="select":
        if len(data)==2:
          (rel, pos) = parse_pos(data[1]) 
          if pos == None:
            return False
        else:
          rel = None
          pos = None
        self._focus.select(rel,pos)
        return True

      return False

  def _swap_view(self):
    if self._focus == self._logsel:
      self._focus = self._filesel
    else:
      self._focus = self._logsel
    self.update()

  def update(self):
    with self._lock:
      self._focus.draw()

class LogSelect(object):
  def __init__(self,window,conf,geom,curseslock,audiobook):
    self._lock = RLock()
    self._window = window
    self._conf = conf
    self._geom = geom
    self._curseslock = curseslock
    self._audiobook = audiobook

    self._focus = None

  def getGeom(self):
    with self._lock:
      return self._geom

  def setGeom(self,geom):
    with self._lock:
      with self._curseslock:
        self._geom = geom

  def move(self,delta):
    with self._lock:
      playlog = self._audiobook.playlog
      self._focus = calc_focus( length = len(playlog),
                                focus = self._focus,
                                delta = delta)
      self.draw()

  def ppage(self):
    with self._lock:
      playlog = self._audiobook.playlog
      num = min(self._geom.h, len(playlog))
      self._focus = calc_ppage( length = len(playlog),
                                num = num,
                                focus = self._focus)
      self.draw()

  def npage(self):
    with self._lock:
      playlog = self._audiobook.playlog
      num = min(self._geom.h, len(playlog))
      self._focus = calc_npage( length = len(playlog),
                                num = num,
                                focus = self._focus)
      self.draw()

  def move_to(self,focus):
    with self._lock:
      playlog = self._audiobook.playlog
      self._focus = calc_focus( length = len(playlog),
                                focus = focus)
      self.draw()

  def select(self,rel,bufpos):
    with self._lock:
      ab = self._audiobook
      playlog = ab.playlog
      if self._focus == None:
        if rel:
          ab.dseek(bufpos)
        elif rel!=None:
          ab.seek(None,bufpos)
      elif self._focus <= len(playlog):
        filename = playlog[self._focus].filename
        position = playlog[self._focus].position
        if rel:
          ab.seek(filename,position+bufpos)
        elif rel!=None:
          ab.seek(filename,bufpos)
        else:
          ab.seek(filename,position)

  def draw(self):
    with self._lock:
      if self._geom.is_sane():
        with self._curseslock:
          self._window.erase()

          playlog = self._audiobook.playlog

          # Make sure the focus index is valid.
          self._focus = calc_focus( length = len(playlog),
                                    focus = self._focus)

          num = min(self._geom.h, len(playlog))
          focus = self._focus

          if focus==None:
            start = max(0, len(playlog)-num)
          else:
            start = max(0, min(len(playlog)-num, focus - num/2))

          for i in xrange(0, num):
            # Position in playlog
            logi = i + start
            # Check if this is the currently selected line
            if logi == focus:
              mark = "-> "
              attr = curses.A_REVERSE
            else:
              mark = "   "
              attr = curses.A_NORMAL

            walltime = time.strftime("%Y-%m-%d %H:%M:%S",
              time.gmtime(playlog[logi].walltime))

            event = playlog[logi].event[:self._conf.event_len]
            event += " " * (self._conf.event_len - len(event))

            # Format all stuff before filename
            part0 = "{mark}{walltime} {event} ".format(
              mark = mark,
              walltime = walltime,
              event = event)

            # Format all stuff after filename
            position = ns_to_str(playlog[logi].position)
            duration = ns_to_str(playlog[logi].duration)

            part2 = " {position} / {duration}".format(
              position=position,
              duration=duration)

            # Compute maximum length of filename
            part1len = max(0, self._geom.w - 1 - len(part0) - len(part2))
            # Take the end of filename, if it is too long.
            part1 = playlog[logi].filename[-part1len:]

            # Combine into complete line.
            pad = " " * (part1len - len(part1))
            line = part0 + part1 + pad + part2

            if self._geom.h>=1:
              self._window.addnstr(i, 0, line, self._geom.w-1,attr)
          self._window.refresh()

class FileSelect(object):
  def __init__(self,window,geom,curseslock,audiobook):
    self._lock = RLock()
    self._window = window
    self._geom = geom
    self._curseslock = curseslock
    self._audiobook = audiobook

    self._focus = None

  def getGeom(self):
    with self._lock:
      return self._geom

  def setGeom(self,geom):
    with self._lock:
      with self._curseslock:
        self._geom = geom

  def move(self,delta):
    with self._lock:
      filelist = self._audiobook.list_files()
      self._focus = calc_focus( length = len(filelist),
                                focus = self._focus,
                                delta = delta)
      self.draw()

  def ppage(self):
    with self._lock:
      filelist = self._audiobook.list_files()
      num = min(self._geom.h, len(filelist))
      self._focus = calc_ppage( length = len(filelist),
                                num = num,
                                focus = self._focus)
      self.draw()

  def npage(self):
    with self._lock:
      filelist = self._audiobook.list_files()
      num = min(self._geom.h, len(filelist))
      self._focus = calc_npage( length = len(filelist),
                                num = num,
                                focus = self._focus)
      self.draw()

  def move_to(self,focus):
    with self._lock:
      filelist = self._audiobook.list_files()
      self._focus = calc_focus( length = len(filelist),
                                focus = focus)
      self.draw()

  def select(self,rel,bufpos):
    with self._lock:
      ab = self._audiobook
      filelist = ab.list_files()
      if self._focus == None:
        if rel:
          ab.dseek(bufpos)
        elif rel!=None:
          ab.seek(None,bufpos)
      elif self._focus <= len(filelist):
        ab.seek(filelist[self._focus],bufpos)

  def draw(self):
    with self._lock:
      if self._geom.is_sane():
        with self._curseslock:
          self._window.erase()

          filelist = self._audiobook.list_files()

          # Make sure the focus index is valid.
          self._focus = calc_focus( length = len(filelist),
                                    focus = self._focus)

          num = min(self._geom.h, len(filelist))
          focus = self._focus

          if focus==None:
            start = max(0, len(filelist)-num)
          else:
            start = max(0, min(len(filelist)-num, focus - num/2))

          for i in xrange(0, num):
            # Position in filelist
            listi = i + start
            # Check if this is the currently selected line
            if listi == focus:
              mark = "-> "
              attr = curses.A_REVERSE
            else:
              mark = "   "
              attr = curses.A_NORMAL

            # Compute maximum length of filename
            part0len = max(0, self._geom.w - 1 - len(mark))
            # Take the end of filename, if it is too long.
            part0 = filelist[listi][-part0len:]

            # Combine into complete line.
            pad = " " * (part0len - len(part0))
            line = mark + part0 + pad

            if self._geom.h>=1:
              self._window.addnstr(i, 0, line, self._geom.w-1,attr)
          self._window.refresh()

def calc_focus(length,focus,delta=0):
  if focus == None:
    if delta>0:
      focus = delta-1
    else:
      focus = delta+length
  else:
    focus += delta
  
  if focus<0 or focus>=length:
    focus = None

  return focus

def calc_ppage(length,num,focus):
  if focus == None:
    focus = length-1

  if focus > length-num/2:
    focus = length-num/2

  return max(0, focus - num)

def calc_npage(length,num,focus):
  if focus == None:
    return None

  if focus < num/2:
    focus = num/2

  newfocus = focus + num
  
  if newfocus > length:
    return None
  else:
    return newfocus

class Reader(gobject.GObject):
  HEIGHT=1

  __gsignals__ = {
    'error' : ( gobject.SIGNAL_RUN_LAST,
                gobject.TYPE_NONE,
                (gobject.TYPE_STRING,)),
    'event' : ( gobject.SIGNAL_RUN_LAST,
              gobject.TYPE_BOOLEAN,
              (gobject.TYPE_STRING,),
              gobject.signal_accumulator_true_handled)
  }

  def __init__(self,curseslock,geom,charmap,fifopath=None):
    gobject.GObject.__init__(self)
    self._lock = RLock()
    self._geom = geom
    self._curseslock = curseslock

    if fifopath == "":
      self._fifopath = None
    else:
      self._fifopath = fifopath

    self._window = geom.newwin()
    self._window.nodelay(1)
    self._window.keypad(1)

    self._charmap = charmap

    self._key = None

    self._quit = Event()
    signal.signal(signal.SIGUSR1, lambda signum, stack_frame: None)
    signal.signal(signal.SIGTERM, lambda signum, stack_frame: exit(0))

    self._clear_timer = Timer(1000,self._clear_key,repeat=False)

    self._buffer = ""

    self.connect("event",self._on_event)

    self.update()

  def run(self):
    self._read()
    #if self._fifopath == None:
    #  self._read()
    #else:
    #  # Create fifo if it does not exist.
    #  fifopath = expanduser(self._fifopath)
    #  if not exists(fifopath):
    #    os.mkfifo(fifopath,0700)
    #  
    #  self._read(fifohandle)

  def _read(self):
    handles = [sys.stdin]

    try:
      while not self._quit.is_set():
        try:
          select.select(handles,[],handles)
        except select.error:
          pass

        if self._quit.is_set():
          break

        while True:
          try:
            with self._lock:
              with self._curseslock:
                ch = self._window.getch()
                if ch == -1:
                  break
                key = curses.keyname(ch)

              self._key = key

              self.update()
              self._clear_timer.start()

              event = self._charmap[key].strip()
              event_formatted = event.format(b=self._buffer)
            if not self.emit("event",event_formatted):
              self.emit('error','Failed to parse: "{0}"'.format(event))
          except (KeyError, IndexError):
            pass
    finally:
      self._quit.set()

  def _on_event(self,obj,event):
    with self._lock:
      eventword = event.split()
      if eventword[0]=="buffer":
        if eventword[1] == "store":
          self._buffer += eventword[2]
          self.update()
          return True
        elif eventword[1] == "erase":
          self._buffer = self._buffer[:-1]
          self.update()
          return True
        elif eventword[1] == "clear":
          self._buffer = ""
          self.update()
          return True

      return False

  def _clear_key(self):
    with self._lock:
      self._key = None
      self.update()

  def quit(self):
    with self._lock:
      if not self._quit.is_set():
        self._quit.set()
        os.kill(os.getpid(), signal.SIGUSR1)

  def getGeom(self):
    with self._lock:
      return self._geom

  def setGeom(self,geom):
    with self._lock:
      with self._curseslock:
        self._geom = geom
        if self._geom.is_sane():
          self._window.resize(geom.h,geom.w)
          self._window.mvwin(geom.y,geom.x)
          self.update()

  def update(self):
    with self._lock:
      if self._geom.is_sane():
        with self._curseslock:
          self._window.erase()
          prefix = "> "
          if self._key!=None:
            keystr = " ({0})".format(self._key)
          else:
            keystr = ""
          maxbuf = self._geom.w - len(keystr) - len(prefix) - 1
          bufstr = self._buffer[-maxbuf:]
          spacing = " "*(maxbuf-len(bufstr))
          line = prefix+bufstr+spacing+keystr
          if self._geom.h>=1:
            self._window.addnstr(0,0,line,self._geom.w-1)
          self._window.refresh()

class Volume(object):
  HEIGHT = 2
  WIDTH = 6

  def __init__(self,curseslock,audiobook,geom):
    self._lock = RLock()
    self._curseslock = curseslock
    self._window = geom.newwin()
    self._gst = audiobook.gst()
    self._geom = geom
    self._gst.connect("notify::volume",self._on_volume)
    self.update()

  def getGeom(self):
    with self._lock:
      return self._geom

  def setGeom(self,geom):
    with self._lock:
      with self._curseslock:
        self._geom = geom
        if self._geom.is_sane():
          self._window.resize(geom.h,geom.w)
          self._window.mvwin(geom.y,geom.x)
          self.update()

  def _on_volume(self,obj,prop):
    with self._lock:
      self.update()

  def update(self):
    with self._lock:
      if self._geom.is_sane():
        try:
          vol = "{0:.0%}".format(self._gst.get_property("volume"))
        except gst.QueryError:
          vol = "--%"
        with self._curseslock:
          self._window.erase()
          if self._geom.h>=1:
            self._window.addnstr(0,0,"  Vol",self._geom.w-1)
          if self._geom.h>=2:
            self._window.addnstr(1,0,"{0:>5}".format(vol),self._geom.w-1)
          self._window.refresh()

class Status(object):
  HEIGHT = 2

  def __init__(self,curseslock,conf,audiobook,geom,interval):
    """Create the audiobook view.
    
    Arguments:
      conf        The parsed program configuration.
      audiobook   The audiobook object to create a view for.
      geom        Geometry of the window.
      interval    How often to show position while playing.
    """
    self._lock = RLock()
    self._curseslock = curseslock
    self._audiobook = audiobook
    self._geom = geom
    with self._lock:
      self._audiobook.connect("position",self._on_position)
      self._audiobook.connect("notify::playing",self._on_playing)
      self._gst = self._audiobook.gst()
      self._window = geom.newwin()
      self._timer = Timer(interval*1000, self._on_timer, repeat=True)
      self.update()

  def getGeom(self):
    with self._lock:
      return self._geom

  def setGeom(self,geom):
    with self._lock:
      with self._curseslock:
        self._geom = geom
        if self._geom.is_sane():
          self._window.resize(geom.h,geom.w)
          self._window.mvwin(geom.y,geom.x)
          self.update()

  def _on_playing(self,ab,prop):
    """Playing state updated.
    
    Arguments:
      ab    The audiobook that this is a view for.
      prop  The property that was updated.
    """
    with self._lock:
      if ab.playing and (not self._timer.started()):
        self._timer.start()
      if (not ab.playing) and self._timer.started():
        self._timer.stop()

  def _on_position(self,ab):
    """A hint has been received that it is a good idea to update the position information.
    
    Arguments:
      ab    The audiobook that this is a view for.
    """
    with self._lock:
      self.update()

  def _on_timer(self):
    with self._lock:
      self.update()

  def update(self):
    with self._lock:
      if self._geom.is_sane():
        (filename,position,duration) = self._audiobook.position()
        if filename == None:
          filename = ""

        if self._audiobook.playing:
          state = "Playing"
        elif self._audiobook.eob:
          state = "End"
        else:
          state = "Paused"

        with self._curseslock:
          prefix = "File: "
          maxchars = self._geom.w - len(prefix) - 1
          first = prefix + filename[-maxchars:]

          second = "{position} / {duration} [{state}]".format(
            position=ns_to_str(position),
            duration=ns_to_str(duration),
            state=state)

          self._window.erase()
          if self._geom.h>=1:
            self._window.addnstr(0,0,first,self._geom.w-1)
          if self._geom.h>=2:
            self._window.addnstr(1,0,second,self._geom.w-1)
          self._window.refresh()

class Geometry(object):
  @staticmethod
  def fromWindow(window):
    return Geometry.fromSizePos(window.getmaxyx(),window.getbegyx())

  @staticmethod
  def fromSizePos(size,pos):
    return Geometry(size[0],size[1],pos[0],pos[1])

  def __init__(self,h,w,y,x):
    self.h = h
    self.w = w
    self.y = y
    self.x = x

  def is_sane(self):
    return self.h>0 and self.w>0 and self.y>=0 and self.x>=0

  def newwin(self,parent=None):
    if parent==None:
      return curses.newwin( self.h,
                            self.w,
                            self.y,
                            self.x)
    else:
      return parent.subwin( self.h,
                            self.w,
                            self.y,
                            self.x)

  def __str__(self):
    return "({g.h},{g.w},{g.y},{g.x})".format(g=self)

class CursesUI(object):
  def __init__(self,conf,directory,stdscr):
    self._lock = RLock()
    self._curseslock = RLock()
    with self._lock:
      self._conf = conf
      self._window = stdscr
      self._audiobook = AudioBook(conf,directory)

      curses.curs_set(0)

      gobject.threads_init()
      self._mainloop = glib.MainLoop()

      if conf.default_bindings:
        charmap = { "^L":"redraw",
                    "q":"quit",
                    " ":"play_pause",
                    "KEY_LEFT":"seek -10",
                    "h":"seek -10",
                    "KEY_RIGHT":"seek +10",
                    "l":"seek +10",
                    "u":"volume +0.1",
                    "d":"volume -0.1",
                    "KEY_UP":"up",
                    "KEY_DOWN":"down",
                    "KEY_HOME":"begin",
                    "KEY_END":"end",
                    "KEY_PPAGE":"ppage",
                    "KEY_NPAGE":"npage",
                    "^I":"swap_view",
                    "*":"mark *",
                    "^J":"select {b}",
                    "1":"buffer store 1",
                    "2":"buffer store 2",
                    "3":"buffer store 3",
                    "4":"buffer store 4",
                    "5":"buffer store 5",
                    "6":"buffer store 6",
                    "7":"buffer store 7",
                    "8":"buffer store 8",
                    "9":"buffer store 9",
                    "0":"buffer store 0",
                    ":":"buffer store :",
                    "+":"buffer store +",
                    "-":"buffer store -",
                    "=":"buffer clear",
                    "KEY_BACKSPACE":"buffer erase"}
      else:
        charmap = {}

      for binding in conf.bind:
        if len(binding)==2:
          charmap[binding[0]] = binding[1]
        elif len(binding)==1:
          del charmap[binding[0]]
                  
      (volume_geom, status_geom, reader_geom, select_geom) = self._compute_geom()

      charmap["KEY_RESIZE"] = "resize"
      self._reader = Reader(curseslock=self._curseslock,
                            geom=reader_geom,
                            charmap=charmap,
                            fifopath=conf.cmdpipe)
      self._reader.connect("event",self._on_event)


      with self._curseslock:
        self._actuator = Actuator(audiobook=self._audiobook,
                                  reader=self._reader)

        self._volume = Volume(curseslock=self._curseslock,
                              audiobook=self._audiobook,
                              geom=volume_geom)

        self._status = Status(curseslock=self._curseslock,
                              conf=conf,
                              audiobook=self._audiobook,
                              geom=status_geom,
                              interval=1)

        self._select = Select(curseslock=self._curseslock,
                              conf=conf,
                              geom=select_geom,
                              audiobook=self._audiobook,
                              reader=self._reader)

      self._gobject_thread = Thread(target=self._mainloop.run,
                                    name="GobjectLoop")

  def getGeom(self):
    with self._lock:
      return Geometry.fromWindow(self._window)

  def _compute_geom(self):
    with self._lock:
      topgeom = self.getGeom()
      volume_geom = Geometry( h=min(Volume.HEIGHT,topgeom.h),
                              w=min(Volume.WIDTH,topgeom.w),
                              y=max(0,topgeom.h-Volume.HEIGHT),
                              x=max(0,topgeom.w-Volume.WIDTH))

      status_geom = Geometry( h=min(Status.HEIGHT,topgeom.h),
                              w=topgeom.w-volume_geom.w,
                              y=max(0,topgeom.h-Status.HEIGHT),
                              x=0)

      statusvol_h = max(Volume.HEIGHT,Status.HEIGHT)

      reader_geom = Geometry(  h=min(Reader.HEIGHT,topgeom.h-statusvol_h),
                              w=topgeom.w,
                              y=max(0,topgeom.h-statusvol_h-Reader.HEIGHT),
                              x=0)

      select_geom = Geometry( h=max(0,topgeom.h-statusvol_h-Reader.HEIGHT),
                              w=topgeom.w,
                              y=0,
                              x=0)

      return (volume_geom,status_geom,reader_geom,select_geom)
      

  def _on_event(self,obj,event):
    data = event.split()
    if len(data)>0:
      cmd = data[0]
      if cmd=="resize":
        with self._lock:
          self._update_layout()
        return True
      elif cmd=="redraw":
        with self._lock:
          self._reader.update()
          self._volume.update()
          self._status.update()
          self._select.update()
        return True
      elif cmd=="quit":
        self.quit()
        return True

      return False
          

  def _update_layout(self):
    with self._lock:
      with self._curseslock:
        (volume_geom,status_geom,reader_geom,select_geom) = self._compute_geom()
        self._reader.setGeom(reader_geom)
        self._volume.setGeom(volume_geom)
        self._status.setGeom(status_geom)
        self._select.setGeom(select_geom)

  def quit(self):
    """Shut down the audiobook player.
    """
    with self._lock:
      self._audiobook.pause()
      self._mainloop.quit()
      self._audiobook.quit()
      self._reader.quit()

  def run(self,filename,position):
    """Run the audiobook player.
    
    Arguments:
      filename  The filename to start playing at. (Or None to let the player
                decide.)

      position  The position to start playing at in nanoseconds. (Or none to
                let the player decide.)
    """
    try:
      self._audiobook.gst().set_property("volume",self._conf.volume)

      if(self._conf.autoplay):
        self._audiobook.play(filename,position)
      else:
        self._audiobook.seek(filename,position)
      self._gobject_thread.start()
      self._reader.run()
    except (KeyboardInterrupt, SystemExit):
      self.quit()

class Actuator(object):
  """A command actuator for the audiobook player.
  """

  def __init__(self,audiobook,reader):
    """Create the actuator

    Arguments:
      audiobook   The audiobook player object to control.
      reader      The reader that emits events.
    """
    self._lock = RLock()
    self._audiobook = audiobook
    self._reader = reader
    self._reader.connect("event",self._on_event)

  def _on_event(self,obj,event):
    with self._lock:
      ab = self._audiobook
      data = event.split()
      if len(data)>0:
        try:
          cmd = data[0]

          if cmd=="play":
            start_file = self._get_file(data)
            (rel, start_pos) = self._get_pos(data)
            ab.play(start_file=start_file,start_pos=start_pos)
            return True

          elif cmd=="pause":
            ab.pause()
            return True

          elif cmd=="seek":
            start_file = self._get_file(data)
            (rel, start_pos) = self._get_pos(data)
            if start_file == None and rel:
              ab.dseek(start_pos)
            else:
              ab.seek(start_file=start_file,start_pos=start_pos)
            return True

          elif cmd=="dseek" and len(data)==2:
            (rel, start_pos) = self._get_pos(data)
            if start_pos != None:
              ab.dseek(start_pos)
            return True

          elif cmd=="stepfile" and len(data)==2:
            delta = int(data[1])
            new_file = ab._get_file(delta)
            if new_file!=None:
              ab.seek(start_file=new_file,start_pos=0)
            return True

          elif cmd=="play_pause" and len(data)==1:
            ab.play_pause()
            return True

          elif (cmd=="volume" or cmd=="dvolume") and len(data)==2:
            raw = data[1]
            if raw[0] == "+" or raw[0] == "-" or cmd == "dvolume":
              gst = self._audiobook.gst()
              oldvol = gst.get_property("volume")
              volume = oldvol + float(raw)
            else:
              volume = float(raw)

            volume = max(0, min(volume, 10))
            gst.set_property("volume",volume)
            return True

          elif cmd=="mark" and len(data)==2:
            self._audiobook.mark(data[1])
            return True

        except ValueError as e:
          pass
      return False

  def _get_file(self,data):
    """Parse a filename from given data.
    
    Arguments:
      data    List of strings representing each word.

    Returns:  Filename, or None if no filename was given.
    """
    if len(data)>=3:
      return " ".join(data[1:-1])
    else:
      return None

  def _get_pos(self,data):
    """Parse position.
    
    Arguments:
      data    List of strings representing each word.

    Returns:  Position, None if no position was given.

    Exceptions:
      ValueError if parsing failed.
    """
    if len(data)>=2:
      (rel, pos) = parse_pos(data[-1])
      if pos == None:
        raise ValueError()
      return (rel, pos)
    else:
      return (None,None)

def run():
  parser = pstorytime.audiobookargs.ArgumentParser(
    description="%(prog)s is a logging console audiobook player.",
    epilog="Paths can contain the strings {conf} and {audiobook}. They are replaced with the absolute path to the configuration directory and the audiobook directory respectively. Arguments can be placed in a configuration file in {conf}/config, or in any file specified on the commandline prefixed by an @ sign. Though the tilde character, {conf} and {audiobook} is not expanded in such paths.",
    add_help=True,
    parents=[pstorytime.audiobookargs.audiobookargs],
    fromfile_prefix_chars="@",
    conflict_handler='resolve')

  parser.add_argument(
    "--cmdpipe",
    help="Path to a pipe that commands are read from relative to current directory. See section on paths. (Default: %(default)s)",
    default="")

  parser.add_argument(
    "--playlog-file",
    help="Path to the file to save playlog in relative to current directory. See section on paths. (Default: %(default)s)",
    default="{conf}/logs/{audiobook}/.playlog")

  parser.add_argument(
    "--conf-dir",
    help="Configuration directory (Default: %(default)s)",
    default="~/.pstorytime")

  parser.add_argument(
    "path",
    help="Audiobook directory, possibly including a file to start playing at. (Default: %(default)s)",
    nargs='?',
    default=".")

  parser.add_argument(
    "position",
    help="Position to start playing at. (Default: %(default)s)",
    nargs='?',
    action=pstorytime.audiobookargs.Position)

  parser.add_argument(
    "--noconf",
    help="Do not read default config file.",
    action='store_true')

  parser.add_argument(
    "--autoplay",
    help="Start playing when the audiobook is started. (Default: %(default)s)",
    action=pstorytime.audiobookargs.Boolean,
    default=False)

  parser.add_argument(
    "--volume",
    help="Playback volume as a float between 0 and 10. (Default: %(default)s)",
    default=1.0,
    type=float)

  parser.add_argument(
    "--default-bindings",
    help="Load default bindings. Otherwise all bindings need to be added manually. (Default: %(default)s)",
    action=pstorytime.audiobookargs.Boolean,
    default=True)

  parser.add_argument(
    "--bind",
    help="Add new binding from key to event. Key names are displayed in the program when pressed, possible events are listed in its own section.",
    nargs=2,
    metavar=('KEY','EVENT'),
    action='append',
    default=[])

  parser.add_argument(
    "--unbind",
    help="Remove binding for the given key. Key names are displayed in the program when pressed.",
    nargs=1,
    metavar='KEY',
    action='append',
    dest='bind',
    default=[])

  parser.add_argument(
    "--event-len",
    help="Number of characters to display of event names in the playlog. (Default: %(default)s)",
    default=8,
    type=int)

  conf = parser.parse_args()

  configfile = expanduser(join(conf.conf_dir,"config"))

  if (not conf.noconf) and isfile(configfile):
    conf = parser.parse_args(["@"+configfile])
    conf = parser.parse_args(namespace=conf)

  if isfile(conf.path):
    directory = dirname(conf.path)
    filename = basename(conf.path)
  elif isdir(conf.path):
    directory = conf.path
    filename = None
  else:
    print("No such file or directory: {0}".format(conf.path))
    exit(1)

  gen = PathGen(conf.conf_dir,directory)
  conf.playlog_file = gen.gen(conf.playlog_file)
  conf.cmdpipe = gen.gen(conf.cmdpipe)

  if conf.cmdpipe==None or conf.cmdpipe=="":
    pipelock = DummyLock()
  else:
    pipelock = FileLock(conf.cmdpipe+".lock")

  dirlock = FileLock(conf.playlog_file+".lock")

  try:
    with pipelock:
      with dirlock:
        def run(stdscr):
          ui = CursesUI(conf,directory,stdscr)
          ui.run(filename,conf.position)
        curses.wrapper(run)
  except LockedException:
    print("Error: Another instance is already using the same files.")
    sys.exit(1)

if __name__ == '__main__':
  run()
