"""AuraFlow 2: one hands-free workspace, automatic camera lifecycle."""
import sys
import time
import math
from pathlib import Path
from PySide6.QtCore import Qt, QTimer, QSettings, QStandardPaths
from PySide6.QtGui import QFont, QShortcut, QKeySequence
from PySide6.QtWidgets import (QMainWindow,QWidget,QVBoxLayout,QHBoxLayout,QGridLayout,
    QDialog,QFormLayout,QSpinBox,QDoubleSpinBox,QCheckBox,QDialogButtonBox,QScrollArea,QComboBox)
from .widgets import Card, VisionView, LevelMeter, label, button
from .workers import CameraWorker, ControlWorker
from .handsfree import HandsFree
from .gestures import Action, analyze
from .demo import landmarks
from .identity import HandIdentity

STYLE='''
QWidget { background:#0a1018; color:#e0eaf2; font-family:'Segoe UI'; font-size:13px; }
QLabel { background:transparent; }
QLabel[role="brand"] { font-size:22px; font-weight:600; letter-spacing:1px; }
QLabel[role="heading"] { font-size:20px; font-weight:600; }
QLabel[role="muted"] { color:#899dae; }
QLabel[role="eyebrow"] { color:#7993a8; font-size:11px; letter-spacing:1px; }
QLabel[role="status"] { color:#7ddde9; font-size:14px; }
QLabel[role="chip"] { color:#7ddde9; background:#122c36; border-radius:10px; padding:7px 12px; font-size:11px; }
QLabel[role="direction"] { color:#dbe8f2; font-size:16px; padding:9px 0; }
QFrame#card { background:#101c28; border:1px solid #20303e; border-radius:14px; }
QPushButton { background:#122130; border:1px solid #293c4e; padding:9px 13px; border-radius:8px; }
QPushButton:hover { background:#1a3243; border-color:#68bfce; }
QPushButton[role="subtle"] { background:transparent; border:0; color:#9bb2c3; padding:6px; }
QSpinBox,QDoubleSpinBox,QComboBox { background:#142333; border:1px solid #293c4e; padding:6px; }
QProgressBar { background:#223444; border:0; border-radius:3px; max-height:5px; min-height:5px; }
QProgressBar::chunk { background:#73cedd; border-radius:3px; }
QScrollArea { border:0; }
QCheckBox { spacing:10px; padding:6px; }
'''

GUIDE=[('01 / PRECISION','Point → move · pinch → click','Use your right hand. Cursor freezes while pinching.'),
       ('02 / LEVELS','Right pinch → volume','Left pinch → brightness. Extend pinky to adjust; fold to lock.'),
       ('03 / PLAYBACK','Left fist → play / pause','Right fist → mute. Five-finger open-palm swipe → previous / next track.'),
       ('04 / NAVIGATION','V sign → vertical scroll','Three-finger horizontal swipe → previous / next browser tab.'),
       ('05 / SPATIAL ZOOM','Pinch with both hands','Spread apart to zoom in; bring together to zoom out. Two fists reset.'),
       ('06 / QUICK ACTIONS','Two V signs → screenshot','Two open palms → show desktop. Left thumbs-up only → pause / resume.'),
       ('07 / APPS','Four fingers → desktop apps','Keep all four fingers up and tuck your thumb across your palm. Swipe right for Alt+Tab or left for Alt+Shift+Tab. Briefly close your hand to repeat.'),
       ('08 / CLOSE','Middle finger only → close app','Tuck thumb and other fingers. Hold one hand steady for 1.2 seconds to send Alt+F4 to the focused window. Save prompts are not dismissed.')]


class MiniCamera(QWidget):
    """Small always-on-top companion; the main window keeps camera ownership."""
    def __init__(self, owner):
        super().__init__(None, Qt.WindowType.Tool | Qt.WindowType.WindowStaysOnTopHint)
        self.owner = owner
        self.setWindowTitle('AuraFlow · Mini camera')
        self.resize(420, 350); self.setMinimumSize(300, 245)
        self.setStyleSheet(STYLE)
        box=QVBoxLayout(self); box.setContentsMargins(10,10,10,10); box.setSpacing(8)
        head=QHBoxLayout(); head.addWidget(label('MINI CAMERA','eyebrow')); head.addStretch()
        self.live=label('CONNECTING','chip'); head.addWidget(self.live)
        restore=button('Dashboard'); restore.clicked.connect(owner.restore_dashboard); head.addWidget(restore)
        box.addLayout(head)
        self.vision=VisionView(); self.vision.show_status=False; self.vision.setMinimumSize(280,180)
        box.addWidget(self.vision,1)
        self.hands=label('No hands in view','muted'); box.addWidget(self.hands)
        self.feedback=label('Opening camera…','status',True); self.feedback.setMinimumHeight(28); box.addWidget(self.feedback)

    def closeEvent(self,event):
        event.accept()
        if not self.owner.closing:
            self.owner.restore_dashboard()


class MainWindow(QMainWindow):
    def __init__(self,demo=False):
        super().__init__()
        self.setWindowTitle('AuraFlow 2.7.1 · Hands-free')
        self.resize(1160,740); self.setMinimumSize(900,680); self.setStyleSheet(STYLE)
        self.settings=QSettings('AuraFlow','HandControl')
        self.identity=HandIdentity(Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppLocalDataLocation))/'AuraFlow'/'hand_profile.json')
        self.verification_enabled=self.settings.value('verify_hands',True,bool)
        threshold=self.settings.value('hand_threshold',.10,float)
        self.identity.threshold=threshold if threshold in (.07,.10,.14) else .10
        self.enrollment_label=None
        self.router=HandsFree()
        self.load_tuning()
        self.camera=None; self.worker=None; self.monitor=None
        self.demo=demo; self.closing=False; self.camera_live=False
        self.ready_at=None; self.last_frame=0; self.demo_start=time.monotonic()
        self.last_error=''; self.current_epoch=0
        self.error_until=0; self.error_message=''
        self.action_until=0; self.action_message=''
        self.mini=None
        self._build()
        if sys.platform=='win32' and not demo:
            from .system import WindowsInput
            self.monitor=WindowsInput(); self.worker=ControlWorker()
            self.worker.result.connect(self.result); self.worker.error.connect(self.error)
            self.worker.start()
        self.timer=QTimer(self); self.timer.timeout.connect(self.tick); self.timer.start(33)
        self.poll=QTimer(self); self.poll.timeout.connect(self.refresh); self.poll.start(4000)
        self.escape=QShortcut(QKeySequence('Escape'),self); self.escape.activated.connect(self.pause)
        if demo:
            self.vision.demo=True; self.state.setText('DEMO')
        else: QTimer.singleShot(150,self.start_camera)

    def _build(self):
        self.scroll=QScrollArea(); self.scroll.setWidgetResizable(True); self.setCentralWidget(self.scroll)
        root=QWidget(); self.scroll.setWidget(root); outer=QVBoxLayout(root)
        outer.setContentsMargins(24,22,24,18); outer.setSpacing(18)
        top=QHBoxLayout(); top.setSpacing(14)
        top.addWidget(label('AuraFlow','brand')); top.addWidget(label('2.7.1  /  Hands-free','muted'))
        my_hands=button('My hands'); my_hands.clicked.connect(self.open_hands); top.addWidget(my_hands)
        top.addStretch()
        mini=button('Mini camera','camera'); mini.clicked.connect(self.open_mini); top.addWidget(mini)
        self.state=label('CONNECTING','chip'); top.addWidget(self.state)
        self.pause_btn=button('Pause','pause'); self.pause_btn.clicked.connect(self.toggle_pause); top.addWidget(self.pause_btn)
        settings=button('Settings','Settings'); settings.clicked.connect(self.open_settings); top.addWidget(settings)
        outer.addLayout(top)
        main=QHBoxLayout(); main.setSpacing(16)
        feed=Card(); feed.box.setContentsMargins(16,16,16,16); feed.box.setSpacing(8)
        feedhead=QHBoxLayout(); feedhead.addWidget(label('Live view'))
        feedhead.addStretch(); self.telemetry=label('Connecting…','muted'); feedhead.addWidget(self.telemetry)
        feed.box.addLayout(feedhead)
        self.vision=VisionView(); self.vision.show_status=False
        feed.box.addWidget(self.vision,1)
        self.hands=label('No hands in view','muted'); self.hands.setWordWrap(True); feed.box.addWidget(self.hands)
        feed.box.addWidget(label('CURRENT ACTION','eyebrow'))
        self.feedback=label('Opening your camera…','status',True); self.feedback.setMinimumHeight(32); feed.box.addWidget(self.feedback)
        main.addWidget(feed,1)
        side=QWidget(); side.setFixedWidth(290); sidebar=QVBoxLayout(side)
        sidebar.setContentsMargins(0,0,0,0); sidebar.setSpacing(14)
        tabs=Card(); tabs.box.setContentsMargins(18,18,18,18); tabs.box.setSpacing(9)
        tabs.box.addWidget(label('TABS & DESKTOP APPS','eyebrow'))
        tabs.box.addWidget(label('Swipe to switch','heading',True))
        tabs.box.addWidget(label('Three fingers → browser tabs','status',True))
        tabs.box.addWidget(label('Four fingers → desktop apps','status',True))
        arrows=QHBoxLayout(); arrows.addWidget(label('← Previous','direction')); arrows.addStretch(); arrows.addWidget(label('Next →','direction')); tabs.box.addLayout(arrows)
        self.tab_status=label('Swipe → loose fist → swipe again. Keep your hand in view.','muted',True); tabs.box.addWidget(self.tab_status)
        tabs.box.addWidget(label('For apps: tuck your thumb across your palm. For music: open all five fingers.','muted',True))
        sidebar.addWidget(tabs)
        levels=Card(); levels.box.setContentsMargins(18,16,18,16); levels.box.setSpacing(16)
        levels.box.addWidget(label('DEVICE LEVELS','eyebrow'))
        self.volume=LevelMeter('Volume'); self.brightness_meter=LevelMeter('Brightness')
        levels.box.addWidget(self.volume); levels.box.addWidget(self.brightness_meter); sidebar.addWidget(levels)
        guide=button('View all gestures  ↗',role='subtle'); guide.clicked.connect(self.open_guide)
        sidebar.addWidget(guide)
        sidebar.addStretch()
        main.addWidget(side); outer.addLayout(main,1)
        foot=QHBoxLayout()
        foot.addWidget(label('Demo · no system actions' if self.demo else 'On-device processing  ·  Ctrl + Alt + P to pause','muted'))
        foot.addStretch()
        self.reconnect=button('Reconnect camera',role='subtle'); self.reconnect.clicked.connect(self.restart_camera)
        foot.addWidget(self.reconnect); self.reconnect.setVisible(not self.demo)
        if self.demo:
            self.demo_choice=QComboBox()
            self.demo_choice.addItems(['Switch apps','Switch tabs','Close app','Two-hand zoom','Volume','Brightness','Pointer','Scroll'])
            self.demo_choice.currentTextChanged.connect(self.reset_demo)
            foot.addWidget(self.demo_choice)
        outer.addLayout(foot)

    def open_mini(self):
        if self.mini is None:
            self.mini=MiniCamera(self)
            size=self.settings.value('mini_size')
            position=self.settings.value('mini_position')
            if size: self.mini.resize(size)
            if position: self.mini.move(position)
        self.mini.show(); self.sync_mini(); self.mini.raise_(); self.mini.activateWindow()
        self.hide()

    def restore_dashboard(self):
        if self.mini is not None:
            self.settings.setValue('mini_size',self.mini.size())
            self.settings.setValue('mini_position',self.mini.pos())
            self.mini.hide()
        if not self.closing:
            self.showNormal(); self.raise_(); self.activateWindow()

    def sync_mini(self):
        if self.mini is None or not self.mini.isVisible(): return
        self.mini.vision.image=self.vision.image
        self.mini.vision.hands=self.vision.hands
        self.mini.vision.demo=self.vision.demo
        self.mini.vision.status=self.vision.status
        self.mini.vision.progress=self.vision.progress
        self.mini.hands.setText(self.hands.text())
        self.mini.feedback.setText(self.feedback.text())
        self.mini.live.setText(self.state.text())
        self.mini.vision.update()

    def open_guide(self):
        was_paused=self.router.paused; self.pause(); self.settings_open=True
        dialog=QDialog(self); dialog.setWindowTitle('Gesture guide'); dialog.resize(640,570)
        box=QVBoxLayout(dialog); box.setContentsMargins(22,22,22,22)
        box.addWidget(label('All gestures','heading'))
        box.addWidget(label('One workspace. Keep your palm facing the camera.','muted'))
        scroll=QScrollArea(); scroll.setWidgetResizable(True); content=QWidget(); grid=QGridLayout(content)
        for i,(_,title,detail) in enumerate(GUIDE):
            card=Card(); card.box.setContentsMargins(14,12,14,12)
            card.box.addWidget(label(title,'status',True)); card.box.addWidget(label(detail,'muted',True))
            grid.addWidget(card,i//2,i%2)
        scroll.setWidget(content); box.addWidget(scroll)
        box.addWidget(label('Hold two-hand quick actions for 1.2 seconds, then briefly close your hands.','muted',True))
        close=QDialogButtonBox(QDialogButtonBox.StandardButton.Close); close.rejected.connect(dialog.reject); box.addWidget(close)
        dialog.exec(); self.settings_open=False; self.router.reset(); self.router.paused=was_paused

    def open_hands(self):
        was_paused=self.router.paused
        self.pause(); self.identity.tracks.clear()
        self.settings_open=True
        dialog=QDialog(self); dialog.setWindowTitle('My hands · local geometry filter'); dialog.resize(500,360)
        box=QVBoxLayout(dialog)
        box.addWidget(label('Enroll your hands','heading'))
        box.addWidget(label('Enroll each hand separately: face your open palm toward the camera, spread all fingers, and hold steady for about 4 seconds. Keep the other hand out of view.','muted',True))
        box.addWidget(label('After enrollment, show an open palm briefly to verify, then change freely between gestures. If tracking is lost, show your open palm again.','muted',True))
        box.addWidget(label('Approximate geometry matching. Similar hands may pass; this does not prove identity. Only joint proportions are stored locally.','muted',True))
        self.enrollment_label=label('Saved: '+(', '.join(self.identity.profiles) or 'none'),'status',True)
        box.addWidget(self.enrollment_label)
        for hand in ('Left','Right'):
            btn=button('Enroll / replace '+hand.lower()+' hand')
            btn.clicked.connect(lambda checked=False,h=hand:self.begin_enrollment(h))
            btn.setEnabled(self.camera_live and not self.demo)
            box.addWidget(btn)
        if self.demo or not self.camera_live:
            box.addWidget(label('Enrollment requires a live camera. Demo never saves hand profiles.','muted',True))
        forget=button('Forget saved hands'); forget.clicked.connect(self.forget_hands); box.addWidget(forget)
        close=QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        close.rejected.connect(dialog.reject); box.addWidget(close)
        dialog.exec()
        self.identity.cancel(); self.enrollment_label=None
        self.settings_open=False; self.router.reset(); self.router.paused=was_paused

    def begin_enrollment(self,hand):
        self.identity.begin(hand)
        self.enrollment_label.setText('Show only your '+hand.lower()+' open palm')

    def forget_hands(self):
        self.identity.cancel()
        try:
            self.identity.save({})
            self.enrollment_label.setText('Profiles removed. Enroll again before using the filter.')
        except OSError:
            self.enrollment_label.setText('Could not remove profiles. Check folder permissions.')

    def reset_demo(self):
        self.demo_start=time.monotonic(); self.router.reset()
        self.action_until=0

    def start_camera(self):
        if self.closing or self.camera is not None or self.demo: return
        self.last_error=''; self.state.setText('CONNECTING'); self.feedback.setText('Opening camera…')
        self.camera=CameraWorker(self.settings.value('camera',0,int),self.settings.value('mirror',True,bool),self.settings.value('swap_hands',False,bool))
        self.camera.ready.connect(self.camera_ready); self.camera.error.connect(self.camera_error)
        self.camera.finished.connect(self.camera_finished); self.camera.start()

    def camera_ready(self):
        if self.closing: return
        self.camera_live=True; self.last_frame=time.monotonic(); self.ready_at=self.last_frame+2
        self.identity.tracks.clear()
        self.router.reset(); self.router.paused=False; self.refresh()

    def camera_error(self,message):
        self.last_error=message; self.feedback.setText(message); self.state.setText('CAMERA UNAVAILABLE')
        self.pause()

    def camera_finished(self):
        self.camera=None; self.camera_live=False; self.ready_at=None
        if self.closing: self.close()
        elif getattr(self,'restart_pending',False):
            self.restart_pending=False; self.start_camera()

    def restart_camera(self):
        if self.demo: return
        self.pause(); self.restart_pending=True
        if self.camera: self.camera.requestInterruption()
        else: self.restart_pending=False; self.start_camera()

    def pause(self):
        self.router.paused=True; self.router.reset(); self.ready_at=None
        if self.worker: self.current_epoch=self.worker.invalidate()
        self.state.setText('PAUSED'); self.pause_btn.setText('Resume')

    def toggle_pause(self):
        if self.router.paused:
            self.router.paused=False; self.router.reset()
        else: self.pause()

    def tick(self):
        if self.closing: return
        now=time.monotonic()
        if self.monitor and (self.monitor.pause_pressed() or (not self.router.paused and self.monitor.corner_stop())):
            self.pause()
        if self.demo:
            choice=self.demo_choice.currentText(); t=now-self.demo_start
            if choice in ('Switch tabs','Switch apps'):
                phase=t%4.4
                if phase<.8 or phase>2.8:
                    groups=[landmarks('neutral' if phase<.8 else 'fist')]
                    poses=[analyze(groups[0],hand='Right')]
                else:
                    direction=1 if int(t/4.4)%2==0 else -1
                    offset=direction*min(.36,max(0,phase-1.0)*.55)-direction*.18
                    groups=[landmarks('four' if choice=='Switch apps' else 'three',dx=offset)]
                    poses=[analyze(groups[0],hand='Right')]
            elif choice=='Close app':
                groups=[landmarks('middle_only' if .6 < t%4.4 < 3.2 else 'neutral')]
                poses=[analyze(groups[0],hand='Right')]
            elif choice=='Two-hand zoom':
                d=.14+.06*math.sin(t)
                groups=[landmarks('point',.15,dx=-d),landmarks('point',.15,dx=d)]
                poses=[analyze(groups[0],hand='Left'),analyze(groups[1],hand='Right')]
            else:
                kind={'Volume':'adjust','Brightness':'adjust','Pointer':'point','Scroll':'peace'}[choice]
                groups=[landmarks(kind,.7,dy=.08*math.sin(t))]
                poses=[analyze(groups[0],hand='Left' if choice=='Brightness' else 'Right')]
            self.vision.hands=groups; self.process(poses,now)
            self.telemetry.setText('Simulated input')
        elif self.camera_live and self.camera:
            packet=self.camera.take_frame()
            if packet:
                image,groups,poses,fps,stamp=packet
                if now-stamp<.3:
                    self.last_frame=stamp; self.vision.image=image; self.vision.hands=groups
                    self.telemetry.setText(f'{fps:.0f} fps')
                    if self.ready_at and now<self.ready_at:
                        self.feedback.setText('Ready in '+str(math.ceil(self.ready_at-now))+'…')
                    else:
                        self.ready_at=None; self.process(poses,now)
            if now-self.last_frame>1.5 and not self.router.paused:
                self.pause(); self.feedback.setText('Tracking interrupted. Left thumbs-up to resume after tracking returns.')
        self.vision.update()
        self.sync_mini()

    def process(self,poses,now):
        if self.identity.pending and not self.demo:
            completed=self.identity.enroll(poses,now)
            if completed:
                self.verification_enabled=True; self.settings.setValue('verify_hands',True)
            if self.enrollment_label: self.enrollment_label.setText(self.identity.status)
            self.vision.status=self.identity.status
            self.vision.progress=len(self.identity.samples)/60
            return
        if self.settings_open: return
        if not self.demo and self.verification_enabled and not self.identity.verify(poses,now):
            self.router.reset()
            if self.worker: self.current_epoch=self.worker.invalidate()
            self.action_until=0
            self.feedback.setText(self.identity.status); self.vision.status=self.identity.status
            self.vision.progress=0
            self.hands.setText('Hand verification required')
            self.state.setText('LOCKED'); self.sync_mini()
            return
        poses=[p for p in poses if p]
        self.hands.setText('   ·   '.join(p.hand+' hand' for p in poses) or 'No hands in view')
        for action in self.router.update(poses,now):
            if action.name=='toggle_pause':
                if self.worker: self.current_epoch=self.worker.invalidate()
            elif self.demo:
                if action.name=='volume': self.volume.set_level(action.value)
                elif action.name=='brightness': self.brightness_meter.set_level(action.value)
                if action.name in ('tab_next','tab_previous','app_next','app_previous','close_app'):
                    self.acknowledge_tab(action.name, demo=True)
            elif self.worker and not self.router.paused:
                self.worker.submit(action,self.settings.value('display',0,int))
        status=self.error_message if now<self.error_until else self.action_message if now<self.action_until else self.router.status
        self.feedback.setText(status); self.vision.status=self.router.status
        self.tab_status.setText('Ready · open your hand for the next gesture.' if self.router.reset_fist_held else 'Close your hand for a moment, then swipe again.' if self.router.tab_blocked or self.router.app_blocked else 'Swipe → loose fist → swipe again. Keep your hand in view.')
        self.vision.progress=self.router.progress
        self.state.setText('DEMO' if self.demo else 'PAUSED' if self.router.paused else 'LIVE')
        self.pause_btn.setText('Resume' if self.router.paused else 'Pause')
        self.sync_mini()

    settings_open=False

    def refresh(self):
        if self.worker:
            self.worker.submit(Action('read_audio')); self.worker.submit(Action('read_display'),self.settings.value('display',0,int))

    def acknowledge_tab(self,name,demo=False):
        direction={'tab_next':'Next tab →','tab_previous':'← Previous tab',
                   'app_next':'Alt + Tab →','app_previous':'← Alt + Shift + Tab',
                   'close_app':'Close request (Alt + F4)'}[name]
        self.action_message=('Demo · ' if demo else 'Shortcut sent · ')+direction
        self.action_until=time.monotonic()+1.1

    def result(self,name,data,epoch):
        if self.worker and epoch != self.worker.epoch: return
        if 'volume' in data: self.volume.set_level(data['volume'])
        if 'muted' in data: self.volume.set_muted(data['muted'])
        if 'brightness' in data: self.brightness_meter.set_level(data['brightness'])
        if name in ('tab_next','tab_previous','app_next','app_previous','close_app'): self.acknowledge_tab(name)

    def error(self,name,message,epoch):
        if self.worker and epoch != self.worker.epoch: return
        self.error_message=message; self.error_until=time.monotonic()+4
        self.feedback.setText(message)
        if name in ('move','click','startup'): self.pause()

    def load_tuning(self):
        self.router.single.low=max(0,self.settings.value('low',.18,float))
        self.router.single.high=max(self.router.single.low+.25,self.settings.value('high',1.15,float))
        self.router.single.smooth=max(.03,min(.3,self.settings.value('smooth',.10,float)))

    def open_settings(self):
        was_paused=self.router.paused; self.pause(); self.settings_open=True
        dialog=QDialog(self); dialog.setWindowTitle('AuraFlow settings'); form=QFormLayout(dialog)
        camera=QSpinBox(); camera.setRange(0,9); camera.setValue(self.settings.value('camera',0,int))
        display=QSpinBox(); display.setRange(0,9); display.setValue(self.settings.value('display',0,int))
        mirror=QCheckBox('Mirror preview'); mirror.setChecked(self.settings.value('mirror',True,bool))
        swap=QCheckBox('Swap anatomical left / right labels'); swap.setChecked(self.settings.value('swap_hands',False,bool))
        verify=QCheckBox('Use enrolled-hand geometry filter'); verify.setChecked(self.verification_enabled)
        sensitivity=QComboBox(); sensitivity.addItems(['Strict','Balanced','Tolerant'])
        sensitivity.setCurrentIndex(min(range(3),key=lambda i:abs((.07,.10,.14)[i]-self.identity.threshold)))
        low=QDoubleSpinBox(); low.setRange(0,.7); low.setSingleStep(.02); low.setValue(self.router.single.low)
        high=QDoubleSpinBox(); high.setRange(.4,2); high.setSingleStep(.05); high.setValue(self.router.single.high)
        smooth=QDoubleSpinBox(); smooth.setRange(.03,.3); smooth.setSingleStep(.01); smooth.setValue(self.router.single.smooth)
        form.addRow('Closed pinch ratio',low); form.addRow('Open pinch ratio',high); form.addRow('Pointer smoothing',smooth)
        form.addRow('Camera',camera); form.addRow('Display',display); form.addRow(mirror); form.addRow(swap)
        form.addRow(verify); form.addRow('Hand matching',sensitivity)
        form.addRow(label('Enroll both hands using My hands. Stricter matching may reject your own gestures. Tolerant matching may accept more other hands.','muted',True))
        form.addRow(label('If your camera already mirrors its image, use Swap labels.\nCamera opens automatically; there is no app permission prompt.','muted',True))
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Save|QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept); buttons.rejected.connect(dialog.reject); form.addRow(buttons)
        accepted=dialog.exec()==QDialog.DialogCode.Accepted
        if accepted:
            self.verification_enabled=verify.isChecked()
            self.identity.threshold=(.07,.10,.14)[sensitivity.currentIndex()]
            self.settings.setValue('verify_hands',self.verification_enabled)
            self.settings.setValue('hand_threshold',self.identity.threshold)
            self.identity.tracks.clear()
            for key,value in [('camera',camera.value()),('display',display.value()),('mirror',mirror.isChecked()),('swap_hands',swap.isChecked()),('low',low.value()),('high',max(low.value()+.25,high.value())),('smooth',smooth.value())]: self.settings.setValue(key,value)
        self.load_tuning()
        self.settings_open=False; self.router.paused=was_paused; self.router.reset()
        if accepted: self.restart_camera()

    def closeEvent(self,event):
        self.closing=True; self.timer.stop(); self.poll.stop()
        if self.mini is not None:
            self.settings.setValue('mini_size',self.mini.size())
            self.settings.setValue('mini_position',self.mini.pos())
            self.mini.hide()
        if self.camera: self.camera.requestInterruption()
        if self.worker: self.worker.stop()
        # Keep Qt and workers alive until their blocking operations finish.
        active=any(w is not None and w.isRunning() for w in (self.camera,self.worker))
        if active:
            event.ignore(); QTimer.singleShot(100,self.close)
        else: event.accept()
