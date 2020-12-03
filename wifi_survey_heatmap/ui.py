"""
The latest version of this package is available at:
<http://github.com/jantman/wifi-survey-heatmap>

##################################################################################
Copyright 2017 Jason Antman <jason@jasonantman.com> <http://www.jasonantman.com>

    This file is part of wifi-survey-heatmap, also known as wifi-survey-heatmap.

    wifi-survey-heatmap is free software: you can redistribute it and/or modify
    it under the terms of the GNU Affero General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.

    wifi-survey-heatmap is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU Affero General Public License for more details.

    You should have received a copy of the GNU Affero General Public License
    along with wifi-survey-heatmap.  If not, see <http://www.gnu.org/licenses/>.

The Copyright and Authors attributions contained herein may not be removed or
otherwise altered, except to add the Author attribution of a contributor to
this work. (Additional Terms pursuant to Section 7b of the AGPL v3)
##################################################################################
While not legally required, I sincerely request that anyone who finds
bugs please submit them at <https://github.com/jantman/wifi-survey-heatmap> or
to me via email, and that you send any contributions or improvements
either as a pull request on GitHub, or to me via email.
##################################################################################

AUTHORS:
Jason Antman <jason@jasonantman.com> <http://www.jasonantman.com>
##################################################################################
"""

import sys
import argparse
import logging
import wx
import json
import os
import subprocess

from wifi_survey_heatmap.collector import Collector

FORMAT = "[%(asctime)s %(levelname)s] %(message)s"
logging.basicConfig(level=logging.WARNING, format=FORMAT)
logger = logging.getLogger()


RESULT_FIELDS = [
    'error',
    'time',
    'timesecs',
    'protocol',
    'num_streams',
    'blksize',
    'omit',
    'duration',
    'sent_bytes',
    'sent_bps',
    'received_bytes',
    'received_bps',
    'sent_kbps',
    'sent_Mbps',
    'sent_kB_s',
    'sent_MB_s',
    'received_kbps',
    'received_Mbps',
    'received_kB_s',
    'received_MB_s',
    'retransmits',
    'bytes',
    'bps',
    'jitter_ms',
    'kbps',
    'Mbps',
    'kB_s',
    'MB_s',
    'packets',
    'lost_packets',
    'lost_percent',
    'seconds'
]


class SurveyPoint(object):

    def __init__(self, parent, x, y):
        self.parent = parent
        self.x = x
        self.y = y
        self.is_finished = False
        self.is_failed = False
        self.progress = 0
        self.result = {}

    def set_result(self, res):
        self.result = res

    @property
    def as_dict(self):
        return {
            'x': self.x,
            'y': self.y,
            'result': self.result,
            'failed': self.is_failed
        }

    def set_is_failed(self):
        self.is_failed = True
        self.progress = 0

    def set_progress(self, value, total):
        self.progress = int(100*value/total)

    def set_is_finished(self):
        self.is_finished = True
        self.progress = 100

    def draw(self, dc, color=None):
        if color is None:
            color = 'green'
            if not self.is_finished:
                color = 'orange'
            if self.is_failed:
                color = 'red'
        dc.SetPen(wx.Pen(color, style=wx.TRANSPARENT))
        dc.SetBrush(wx.Brush(color, wx.SOLID))
        dc.DrawCircle(self.x, self.y, 20)

        # Put progress label on top of the circle
        dc.DrawLabel("{}%".format(self.progress), wx.Rect(
            self.x-10, self.y-10, 20, 20), wx.ALIGN_CENTER)

    def erase(self, dc):
        """quicker than redrawing, since DC doesn't have persistence"""
        dc.SetPen(wx.Pen('white', style=wx.TRANSPARENT))
        dc.SetBrush(wx.Brush('white', wx.SOLID))
        dc.DrawCircle(self.x, self.y, 22)

    def includes_point(self, x, y):
        if (
            self.x - 20 <= x <= self.x + 20 and
            self.y - 20 <= y <= self.y + 20
        ):
            return True
        return False


class SafeEncoder(json.JSONEncoder):

    def default(self, obj):
        if isinstance(obj, type(b'')):
            return obj.decode()
        return json.JSONEncoder.default(self, obj)


class FloorplanPanel(wx.Panel):

    def __init__(self, parent):
        super(FloorplanPanel, self).__init__(parent)
        self.parent = parent
        self.img_path = parent.img_path
        self.Bind(wx.EVT_ERASE_BACKGROUND, self.OnEraseBackground)
        self.Bind(wx.EVT_LEFT_UP, self.onLeftUp)
        self.Bind(wx.EVT_LEFT_DOWN, self.onLeftDown)
        self.Bind(wx.EVT_MOTION, self.onMotion)
        self.Bind(wx.EVT_RIGHT_UP, self.onRightClick)
        self.Bind(wx.EVT_PAINT, self.on_paint)
        self.survey_points = []
        self._moving_point = None
        self._moving_x = None
        self._moving_y = None
        self.data_filename = '%s.json' % self.parent.survey_title
        if os.path.exists(self.data_filename):
            self._load_file(self.data_filename)
        self._duration = self.parent.duration
        self.collector = Collector(
            self.parent.interface, self.parent.server, self._duration)
        self.parent.SetStatusText("Ready.")

    def _load_file(self, fpath):
        with open(fpath, 'r') as fh:
            raw = fh.read()
        data = json.loads(raw)
        for point in data:
            p = SurveyPoint(self, point['x'], point['y'])
            p.set_result(point['result'])
            p.set_is_finished()
            self.survey_points.append(p)

    def OnEraseBackground(self, evt):
        """Add a picture to the background"""
        dc = evt.GetDC()
        if not dc:
            dc = wx.ClientDC(self)
            rect = self.GetUpdateRegion().GetBox()
            dc.SetClippingRect(rect)
        dc.Clear()
        bmp = wx.Bitmap(self.img_path)
        dc.DrawBitmap(bmp, 0, 0)

    def onRightClick(self, event):
        x, y = event.GetPosition()
        point = None
        for p in self.survey_points:
            # important to iterate the whole list, so we find the most recent
            if p.includes_point(x, y):
                point = p
        if point is None:
            self.parent.SetStatusText(
                f"No survey point found at ({x}, {y})"
            )
            self.Refresh()
            return
        # ok, we have a point to remove
        point.draw(wx.ClientDC(self), color='blue')
        res = self.YesNo(f'Remove point at ({x}, {y}) shown in blue?')
        if not res:
            self.parent.SetStatusText('Not removing point.')
            self.Refresh()
            return
        self.survey_points.remove(point)
        self.parent.SetStatusText(f'Removed point at ({x}, {y})')
        self.Refresh()
        self._write_json()

    def onLeftDown(self, event):
        x, y = event.GetPosition()
        point = None
        for p in self.survey_points:
            # important to iterate the whole list, so we find the most recent
            if p.includes_point(x, y):
                point = p
        if point is None:
            self.parent.SetStatusText(
                f"No survey point found at ({x}, {y})"
            )
            self.Refresh()
            return
        self._moving_point = point
        self._moving_x = point.x
        self._moving_y = point.y
        point.draw(wx.ClientDC(self), color='blue')

    def onLeftUp(self, event):
        if self._moving_point is None:
            self._do_measurement(event.GetPosition())
            return
        x, y = event.GetPosition()
        oldx = self._moving_point.x
        oldy = self._moving_point.y
        self._moving_point.x = x
        self._moving_point.y = y
        self._moving_point.draw(wx.ClientDC(self), color='red')
        res = self.YesNo(
            f'Move point from blue ({oldx}, {oldy}) to red ({x}, {y})?'
        )
        if not res:
            self._moving_point.x = self._moving_x
            self._moving_point.y = self._moving_y
        self._moving_point = None
        self._moving_x = None
        self._moving_y = None
        self.Refresh()
        self._write_json()

    def onMotion(self, event):
        if self._moving_point is None:
            return
        x, y = event.GetPosition()
        dc = wx.ClientDC(self)
        self._moving_point.erase(dc)
        self._moving_point.x = x
        self._moving_point.y = y
        self._moving_point.draw(dc, color='red')

    def _check_bssid(self):
        # Return early if BSSID is not to be verified
        if self.parent.bssid is None:
            return True
        # Get BSSID from link
        bssid = self.collector.get_bssid()
        # Compare BSSID, exit early on match
        if bssid == self.parent.bssid:
            return True
        # Error logging
        msg = f'ERROR: Expected BSSID {self.parent.bssid} but found ' \
              f'BSSID {bssid}'
        self.parent.SetStatusText(msg)
        self.Refresh()
        self.warn(msg)
        return False

    def _do_measurement(self, pos):
        self.parent.SetStatusText('Got click at: %s' % pos)
        self.survey_points.append(SurveyPoint(self, pos[0], pos[1]))
        self.Refresh()
        res = {}
        count = 0
        # Number of steps in total (for the progress computation)
        steps = 10
        # Check if we are connected to an AP, all the
        # rest doesn't any sense otherwise
        if not self.collector.check_associated():
            return
        # Check BSSID
        if not self._check_bssid():
            return
        for protoname, udp in {'tcp': False, 'udp': True}.items():
            for suffix, reverse in {'': False, '-reverse': True}.items():
                count += 1

                # Update progress mark
                self.survey_points[-1].set_progress(count, steps)

                # Check if we're still connected to the same AP
                if not self._check_bssid():
                    return

                # Start iperf test
                tmp = self.run_iperf(count, udp, reverse)
                if tmp is None:
                    # bail out; abort this survey point
                    del self.survey_points[-1]
                    self.parent.SetStatusText('Aborted; ready to retry...')
                    self.Refresh()
                    return
                # else success
                res['%s%s' % (protoname, suffix)] = {
                    x: getattr(tmp, x, None) for x in RESULT_FIELDS
                }

        # Check if we're still connected to the same AP
        if not self._check_bssid():
            del self.survey_points[-1]
            return

        # Get SSID
        self.parent.SetStatusText('Obtaining AP name...')
        self.Refresh()
        res['ssid'] = self.collector.get_ssid()
        self.survey_points[-1].set_progress(4, steps)

        # Check if we're still connected to the same AP
        if not self._check_bssid():
            del self.survey_points[-1]
            return

        # Get signal strength
        self.parent.SetStatusText('Obtaining signal strength...')
        self.Refresh()
        res['rss'] = self.collector.get_rss()
        self.survey_points[-1].set_progress(5, steps)

        # Check if we're still connected to the same AP
        if not self._check_bssid():
            del self.survey_points[-1]
            return

        # Get signal frequency
        self.parent.SetStatusText('Getting signal frequency...')
        self.Refresh()
        res['freq'] = self.collector.get_freq()
        self.survey_points[-1].set_progress(6, steps)

        # Check if we're still connected to the same AP
        if not self._check_bssid():
            del self.survey_points[-1]
            return

        # Derive signal channel from frequency
        self.parent.SetStatusText('Getting signal channel...')
        self.Refresh()
        res['chan'] = self.collector.get_channel(res['freq'])
        self.survey_points[-1].set_progress(7, steps)

        # Check if we're still connected to the same AP
        if not self._check_bssid():
            del self.survey_points[-1]
            return

        # Get channel width (in MHz)
        self.parent.SetStatusText('Getting channel width...')
        self.Refresh()
        res['chan_width'] = self.collector.get_channel_width()
        self.survey_points[-1].set_progress(8, steps)

        # Check if we're still connected to the same AP
        if not self._check_bssid():
            del self.survey_points[-1]
            return

        # Get current bitrate (in MBit/s)
        self.parent.SetStatusText('Getting bitrate...')
        self.Refresh()
        res['channel_bitrate'] = self.collector.get_bitrate()
        self.survey_points[-1].set_progress(9, steps)

        # Check if we're still connected to the same AP
        if not self._check_bssid():
            del self.survey_points[-1]
            return

        # Scan APs in the neighborhood
        if self.parent.scan:
            self.parent.SetStatusText('Running iwscan...')
            self.Refresh()
            res['iwscan'] = self.collector.run_iwscan()
            if res['iwscan'] is None:
                del self.survey_points[-1]
                return
        self.survey_points[-1].set_progress(10, steps)

        # Save results and mark survey point as complete
        self.survey_points[-1].set_result(res)
        self.survey_points[-1].set_is_finished()
        self.parent.SetStatusText(
            'Saving to: %s' % self.data_filename
        )
        self.Refresh()
        self._write_json()
        self._ding()

    def _ding(self):
        if self.parent.ding_path is None:
            return
        subprocess.call([self.parent.ding_command, self.parent.ding_path])

    def _write_json(self):
        res = json.dumps(
            [x.as_dict for x in self.survey_points],
            cls=SafeEncoder
        )
        with open(self.data_filename, 'w') as fh:
            fh.write(res)
        self.parent.SetStatusText(
            'Saved to %s; ready...' % self.data_filename
        )
        self.Refresh()

    def warn(self, message, caption='Warning!'):
        dlg = wx.MessageDialog(self.parent, message, caption,
                               wx.OK | wx.ICON_WARNING)
        dlg.ShowModal()
        dlg.Destroy()

    def YesNo(self, question, caption='Yes or no?'):
        dlg = wx.MessageDialog(self.parent, question, caption,
                               wx.YES_NO | wx.ICON_QUESTION)
        result = dlg.ShowModal() == wx.ID_YES
        dlg.Destroy()
        return result

    def run_iperf(self, count, udp, reverse):
        proto = "UDP" if udp else "TCP"
        # iperf3 default direction is uploading to the server
        direction = "Download" if reverse else "Upload"
        self.parent.SetStatusText(
            'Running iperf %d/4: %s (%s) - takes %i seconds' % (count,
                                                                direction,
                                                                proto,
                                                                self._duration)
        )
        self.Refresh()
        tmp = self.collector.run_iperf(udp, reverse)
        if tmp.error is None:
            return tmp
        # else this is an error
        if tmp.error.startswith('unable to connect to server'):
            self.warn(
                'ERROR: Unable to connect to iperf server. Aborting.'
            )
            return None
        if self.YesNo('iperf error: %s. Retry?' % tmp.error):
            self.Refresh()
            return self.run_iperf(count, udp, reverse)
        # else bail out
        return tmp

    def on_paint(self, event=None):
        dc = wx.ClientDC(self)
        for p in self.survey_points:
            p.draw(dc)


class MainFrame(wx.Frame):

    def __init__(
            self, img_path, interface, server, survey_title, scan, bssid, ding,
            ding_command, duration, *args, **kw
    ):
        super(MainFrame, self).__init__(*args, **kw)
        self.img_path = img_path
        self.interface = interface
        self.server = server
        self.scan = scan
        self.survey_title = survey_title
        self.bssid = bssid
        if self.bssid is not None:
            self.bssid = self.bssid.lower()
        self.ding_path = ding
        self.ding_command = ding_command
        self.duration = duration
        self.CreateStatusBar()
        self.pnl = FloorplanPanel(self)
        self.makeMenuBar()

    def makeMenuBar(self):
        fileMenu = wx.Menu()
        fileMenu.AppendSeparator()
        exitItem = fileMenu.Append(wx.ID_EXIT)
        menuBar = wx.MenuBar()
        menuBar.Append(fileMenu, "&File")
        self.SetMenuBar(menuBar)
        self.Bind(wx.EVT_MENU, self.OnExit,  exitItem)

    def OnExit(self, event):
        """Close the frame, terminating the application."""
        self.Close(True)


def parse_args(argv):
    """
    parse arguments/options

    this uses the new argparse module instead of optparse
    see: <https://docs.python.org/2/library/argparse.html>
    """
    p = argparse.ArgumentParser(description='wifi survey data collection UI')
    p.add_argument('-v', '--verbose', dest='verbose', action='count', default=0,
                   help='verbose output. specify twice for debug-level output.')
    p.add_argument('-S', '--no-scan', dest='scan', action='store_false',
                   default=True, help='skip access point scan')
    p.add_argument('-b', '--bssid', dest='bssid', action='store', type=str,
                   default=None, help='Restrict survey to this BSSID')
    p.add_argument('--ding', dest='ding', action='store', type=str,
                   default=None,
                   help='Path to audio file to play when measurement finishes')
    p.add_argument('--ding-command', dest='ding_command', action='store',
                   type=str, default='/usr/bin/paplay',
                   help='Path to ding command')
    p.add_argument('-d', '--duration', dest='duration', action='store',
                   type=int, default=10,
                   help='Duration of each individual ipref test run')
    p.add_argument('INTERFACE', type=str, help='Wireless interface name')
    p.add_argument('SERVER', type=str, help='iperf3 server IP or hostname')
    p.add_argument('IMAGE', type=str, help='Path to background image')
    p.add_argument(
        'TITLE', type=str, help='Title for survey (and data filename)'
    )
    args = p.parse_args(argv)
    return args


def set_log_info():
    """set logger level to INFO"""
    set_log_level_format(logging.INFO,
                         '%(asctime)s %(levelname)s:%(name)s:%(message)s')


def set_log_debug():
    """set logger level to DEBUG, and debug-level output format"""
    set_log_level_format(
        logging.DEBUG,
        "%(asctime)s [%(levelname)s %(filename)s:%(lineno)s - "
        "%(name)s.%(funcName)s() ] %(message)s"
    )


def set_log_level_format(level, format):
    """
    Set logger level and format.

    :param level: logging level; see the :py:mod:`logging` constants.
    :type level: int
    :param format: logging formatter format string
    :type format: str
    """
    formatter = logging.Formatter(fmt=format)
    logger.handlers[0].setFormatter(formatter)
    logger.setLevel(level)


def main():
    args = parse_args(sys.argv[1:])

    # set logging level
    if args.verbose > 1:
        set_log_debug()
    elif args.verbose == 1:
        set_log_info()

    app = wx.App()
    frm = MainFrame(
        args.IMAGE, args.INTERFACE, args.SERVER, args.TITLE, args.scan,
        args.bssid, args.ding, args.ding_command, args.duration, None,
        title='wifi-survey: %s' % args.TITLE,
    )
    frm.Show()
    frm.Maximize(True)
    frm.SetStatusText('%s' % frm.pnl.GetSize())
    app.MainLoop()


if __name__ == '__main__':
    main()
