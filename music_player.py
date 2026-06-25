import sys
import os

import pygame
import mutagen

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QSlider, QLabel, QListWidget, QFileDialog,
    QStyle, QAbstractItemView, QMessageBox,
)

# 支持的文件扩展名
SUPPORTED_EXTS = {".mp3", ".wav", ".flac", ".ogg", ".m4a", ".aac", ".wma", ".mid"}


def get_audio_duration(path: str) -> float:
    """用 mutagen 获取音频时长（秒），失败返回 0。"""
    try:
        audio = mutagen.File(path)
        if audio and audio.info.length:
            return audio.info.length
    except Exception:
        pass
    return 0


class MusicPlayer(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("音乐播放器")
        self.resize(800, 500)

        # 初始化 pygame 混音器
        try:
            pygame.mixer.init()
        except pygame.error as e:
            QMessageBox.critical(self, "初始化失败", f"音频系统初始化失败：{e}")
            sys.exit(1)

        self._files: list[str] = []
        self._current_index = -1
        self._song_length = 0.0       # 秒
        self._playing = False
        self._paused = False

        # 定时器：周期性更新进度条 / 检测歌曲结束
        self._timer = QTimer(self)
        self._timer.setInterval(200)
        self._timer.timeout.connect(self._tick)

        self._init_ui()

    # ─── UI 构建 ───

    def _init_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setSpacing(10)

        # 歌曲信息
        self.song_label = QLabel("未选择歌曲")
        self.song_label.setAlignment(Qt.AlignCenter)
        self.song_label.setStyleSheet("font-size: 16px; padding: 8px;")
        layout.addWidget(self.song_label)

        # 进度条
        prog_layout = QHBoxLayout()
        self.position_slider = QSlider(Qt.Horizontal)
        self.position_slider.setRange(0, 0)
        self.position_slider.sliderMoved.connect(self._seek)

        self.time_label = QLabel("00:00 / 00:00")
        tf = self.time_label.font()
        tf.setFamily("Consolas")
        self.time_label.setFont(tf)

        prog_layout.addWidget(self.position_slider)
        prog_layout.addWidget(self.time_label)
        layout.addLayout(prog_layout)

        # 控制按钮
        controls = QHBoxLayout()
        controls.setSpacing(6)

        self.btn_add = QPushButton("添加歌曲")
        self.btn_prev = QPushButton()
        self.btn_prev.setIcon(self.style().standardIcon(QStyle.SP_MediaSkipBackward))
        self.btn_play = QPushButton()
        self.btn_play.setIcon(self.style().standardIcon(QStyle.SP_MediaPlay))
        self.btn_next = QPushButton()
        self.btn_next.setIcon(self.style().standardIcon(QStyle.SP_MediaSkipForward))
        self.btn_stop = QPushButton()
        self.btn_stop.setIcon(self.style().standardIcon(QStyle.SP_MediaStop))

        controls.addWidget(self.btn_add)
        controls.addStretch()
        controls.addWidget(self.btn_prev)
        controls.addWidget(self.btn_play)
        controls.addWidget(self.btn_next)
        controls.addWidget(self.btn_stop)
        controls.addStretch()

        # 音量
        vol_layout = QHBoxLayout()
        vol_layout.setSpacing(4)
        vol_layout.addWidget(QLabel("音量"))
        self.vol_slider = QSlider(Qt.Horizontal)
        self.vol_slider.setRange(0, 100)
        self.vol_slider.setValue(50)
        self.vol_slider.valueChanged.connect(self._set_volume)
        pygame.mixer.music.set_volume(0.5)
        vol_layout.addWidget(self.vol_slider)

        controls.addLayout(vol_layout)
        layout.addLayout(controls)

        # 播放列表
        self.list_widget = QListWidget()
        self.list_widget.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.list_widget.doubleClicked.connect(self._play_selected)
        layout.addWidget(self.list_widget, stretch=1)

        # 信号连接
        self.btn_add.clicked.connect(self._add_files)
        self.btn_play.clicked.connect(self._toggle_play)
        self.btn_stop.clicked.connect(self._stop)
        self.btn_next.clicked.connect(self._next)
        self.btn_prev.clicked.connect(self._prev)

    # ─── 文件操作 ───

    def _add_files(self):
        files, _ = QFileDialog.getOpenFileNames(
            self, "选择音乐文件", "",
            "音频文件 (*.mp3 *.wav *.flac *.ogg *.m4a *.aac *.wma);;所有文件 (*)"
        )
        for path in files:
            ext = os.path.splitext(path)[1].lower()
            if ext not in SUPPORTED_EXTS:
                continue
            self._files.append(path)
            self.list_widget.addItem(os.path.basename(path))

    # ─── 播放控制 ───

    def _play_index(self, index: int):
        """加载并播放指定索引的歌曲。"""
        if not self._files or index < 0 or index >= len(self._files):
            return

        # 停止当前播放
        self._timer.stop()
        pygame.mixer.music.stop()

        path = self._files[index]
        try:
            pygame.mixer.music.load(path)
            pygame.mixer.music.play()
        except pygame.error as e:
            QMessageBox.warning(self, "播放失败",
                                f"无法播放文件：{os.path.basename(path)}\n{e}")
            self._reset_ui()
            return

        self._current_index = index
        self._playing = True
        self._paused = False
        self._song_length = get_audio_duration(path)

        total_ms = max(1, int(self._song_length * 1000))
        self.position_slider.setRange(0, total_ms)
        self.position_slider.setValue(0)

        self.song_label.setText(f"正在播放：{os.path.basename(path)}")
        self.list_widget.setCurrentRow(index)
        self._timer.start()
        self._update_play_button()

    def _play_selected(self):
        idx = self.list_widget.currentRow()
        if idx >= 0:
            self._play_index(idx)

    def _toggle_play(self):
        if not self._files:
            return
        if self._playing and not self._paused:
            try:
                pygame.mixer.music.pause()
            except pygame.error:
                pass
            self._paused = True
            self._timer.stop()
        elif self._paused:
            try:
                pygame.mixer.music.unpause()
            except pygame.error:
                pass
            self._paused = False
            self._timer.start()
        else:
            idx = self._current_index if self._current_index >= 0 else 0
            self._play_index(idx)
        self._update_play_button()

    def _stop(self):
        self._timer.stop()
        try:
            pygame.mixer.music.stop()
        except pygame.error:
            pass
        self._playing = False
        self._paused = False
        self._reset_ui()
        self._update_play_button()

    def _next(self):
        if not self._files:
            return
        self._play_index((self._current_index + 1) % len(self._files))

    def _prev(self):
        if not self._files:
            return
        self._play_index((self._current_index - 1) % len(self._files))

    def _seek(self, pos_ms: int):
        """进度条拖拽时跳转。"""
        if not self._playing:
            return
        try:
            pygame.mixer.music.rewind()
            pygame.mixer.music.set_pos(pos_ms / 1000.0)
        except pygame.error:
            pass

    def _set_volume(self, value: int):
        try:
            pygame.mixer.music.set_volume(value / 100.0)
        except pygame.error:
            pass

    # ─── 定时轮询 ───

    def _tick(self):
        """定时器回调：更新进度条 + 检测歌曲结束。"""
        if not self._playing or self._paused:
            return

        # 检测歌曲是否结束（pygame.event.get() 在 Windows 上与 Qt 事件循环冲突，
        # 因此使用 get_busy() + get_pos() 代替 set_endevent）
        try:
            busy = pygame.mixer.music.get_busy()
        except pygame.error:
            self._on_song_end()
            return

        if not busy:
            self._on_song_end()
            return

        try:
            pos = pygame.mixer.music.get_pos()
        except pygame.error:
            pos = -1

        if pos >= 0:
            self.position_slider.setValue(pos)

        total_ms = int(self._song_length * 1000)
        self._update_time_label(max(0, pos), total_ms)

    def _on_song_end(self):
        self._timer.stop()
        self.position_slider.setValue(0)
        self._next()   # 自动下一首

    # ─── UI 辅助 ───

    def _reset_ui(self):
        self.position_slider.setValue(0)
        self.position_slider.setRange(0, 0)
        self.time_label.setText("00:00 / 00:00")
        self.song_label.setText("已停止")

    def _update_time_label(self, pos_ms: int, total_ms: int):
        def fmt(ms: int) -> str:
            s = ms // 1000
            m, s = divmod(s, 60)
            return f"{m:02d}:{s:02d}"
        self.time_label.setText(f"{fmt(pos_ms)} / {fmt(total_ms)}")

    def _update_play_button(self):
        icon = QStyle.SP_MediaPause if (self._playing and not self._paused) else QStyle.SP_MediaPlay
        self.btn_play.setIcon(self.style().standardIcon(icon))

    def closeEvent(self, event):
        self._timer.stop()
        try:
            pygame.mixer.music.stop()
            pygame.mixer.quit()
        except pygame.error:
            pass
        event.accept()


def main():
    pygame.mixer.pre_init(44100, -16, 2, 2048)
    app = QApplication(sys.argv)
    player = MusicPlayer()
    player.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()