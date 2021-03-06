# -*- coding: utf-8 -*-
"""Parser for the arguments concerning the audiobook API, leaving out all interface-centric options.
"""

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

import argparse

class FromCommaList(argparse.Action):
  """Generate a list strings from a string of comma separated strings.
  """
  def __call__(self, parser, namespace, values, option_string=None):
    separated = values.split(",")
    setattr(namespace, self.dest, separated)

class Position(argparse.Action):
  """Parse a position given as colon-separated integers.
  """
  def __call__(self, parser, namespace, values, option_string=None):
    if values == None:
      setattr(namespace, self.dest, None)
    else:
      position = pstorytime.misc.parse_pos(values)
      if position==None:
        raise argparse.ArgumentError(self,"Invalid file position: {0}".format(values))
      else:
        setattr(namespace, self.dest, position[1])

class Boolean(argparse.Action):
  """Parse a boolean from a string.
  """
  def __call__(self, parser, namespace, values, option_string=None):
    if values == None:
      setattr(namespace, self.dest, None)
    else:
      if values.lower() in ["true","t","1"]:
        setattr(namespace, self.dest, True)
      elif values.lower() in ["false","f","0"]:
        setattr(namespace, self.dest, False)
      else:
        raise argparse.ArgumentError(self,"Invalid boolean: {0}".format(values))

class ArgumentParser(argparse.ArgumentParser):
  """An alternative argument parser, that allows multiple arguments on the same line.
  """
  def convert_arg_line_to_args(self, arg_line):
    for arg in arg_line.split():
      if not arg.strip():
        continue
      yield arg

audiobookargs = ArgumentParser(
  add_help=False,
  fromfile_prefix_chars="@")

audiobookargs.add_argument(
  "--playlog-file",
  help="Path to the file to save playlog in relative to current directory. (Default: %(default)s)",
  default=".playlog")

audiobookargs.add_argument(
  "--extensions",
  help="Comma separated list of additional extensions to treat as audiobook files. (Default: None)",
  default=[],
  action=FromCommaList)

audiobookargs.add_argument(
  "--autolog-interval",
  help="How often (in seconds) the position should be autosaved so that the position can be recovered upon crashes, including loss of power etc. (Default: %(default)s)",
  default=60,
  type=int)

audiobookargs.add_argument(
  "--backtrack",
  help="How far (in seconds) to automatically backtrack after pausing. (Default: %(default)s)",
  default=10,
  type=int)
