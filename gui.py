"""
HY-TEK Meet Results Viewer GUI

PySide6 GUI with persistent SQLite database.
Supports saving results and managing multiple meets.
"""

import sys
import sqlite3
import json
import csv
from pathlib import Path

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QTabWidget, QTableWidget, QTableWidgetItem, QHeaderView,
    QLabel, QPushButton, QComboBox, QLineEdit, QCheckBox,
    QFileDialog, QMessageBox, QDialog, QGroupBox, QStatusBar,
    QMenuBar, QMenu, QAbstractItemView, QDateEdit
)
from PySide6.QtCore import Qt, QTimer, QDate
from PySide6.QtGui import QAction, QColor, QKeySequence, QIcon

from hytek_parser import parse_hytek_pdf

# Persistent database location
DB_DIR = Path.home() / ".hytek_results"
DB_PATH = DB_DIR / "results.db"


def normalize_date(date_str):
    """Convert date string to ISO format (YYYY-MM-DD) for proper sorting/comparison"""
    if not date_str:
        return None
    import re
    # Already ISO format
    if re.match(r'^\d{4}-\d{2}-\d{2}$', date_str):
        return date_str
    # M/D/YYYY or MM/DD/YYYY
    m = re.match(r'^(\d{1,2})/(\d{1,2})/(\d{4})$', date_str)
    if m:
        return f"{m.group(3)}-{int(m.group(1)):02d}-{int(m.group(2)):02d}"
    return date_str


class RelayDetailsDialog(QDialog):
    """Dialog to show relay swimmers and save legs as individual swims"""

    def __init__(self, parent, row_data, db_path, read_only=False):
        super().__init__(parent)
        self.row_data = row_data
        self.db_path = db_path
        self.read_only = read_only
        self.selected_legs = set()

        self.setWindowTitle(f"Relay Details - {row_data['team']}")
        self.setMinimumSize(600, 400)
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)

        # Header
        header = QLabel(f"<b>{self.row_data['event_name']}</b>")
        header.setStyleSheet("font-size: 14px;")
        layout.addWidget(header)

        place = int(self.row_data['place']) if self.row_data['place'] else '-'
        info = QLabel(f"Team: {self.row_data['team']}  |  Place: {place}  |  Time: {self.row_data['finals_time']}")
        layout.addWidget(info)

        # Swimmers table
        layout.addWidget(QLabel("<b>Relay Swimmers:</b>"))

        self.table = QTableWidget()

        # Parse relay swimmers and splits
        relay_swimmers = json.loads(self.row_data['relay_swimmers']) if self.row_data['relay_swimmers'] else []
        splits = json.loads(self.row_data['splits']) if self.row_data['splits'] else []

        # Calculate leg times
        self.leg_times = self.calculate_leg_times(splits, len(relay_swimmers), self.row_data['event_distance'])
        self.relay_swimmers = relay_swimmers

        if self.read_only:
            # Read-only: no checkboxes, just Leg | Name | Year | Split Time
            self.table.setColumnCount(4)
            self.table.setHorizontalHeaderLabels(['Leg', 'Name', 'Year', 'Split Time'])
            self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
            self.table.setSelectionBehavior(QAbstractItemView.SelectRows)

            self.table.setRowCount(len(relay_swimmers))
            for i, swimmer in enumerate(relay_swimmers):
                name, year, leg = swimmer[0], swimmer[1], swimmer[2]
                leg_time = self.format_time(self.leg_times[i]) if i < len(self.leg_times) and self.leg_times[i] else ""
                self.table.setItem(i, 0, QTableWidgetItem(str(leg)))
                self.table.setItem(i, 1, QTableWidgetItem(name))
                self.table.setItem(i, 2, QTableWidgetItem(year or ''))
                self.table.setItem(i, 3, QTableWidgetItem(leg_time))

            self.table.setColumnWidth(0, 40)
            self.table.setColumnWidth(2, 50)
            self.table.setColumnWidth(3, 100)
        else:
            # Editable: checkboxes for saving individual legs
            self.table.setColumnCount(5)
            self.table.setHorizontalHeaderLabels(['', 'Leg', 'Name', 'Year', 'Split Time'])
            self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
            self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
            self.table.cellClicked.connect(self.on_cell_clicked)

            self.table.setRowCount(len(relay_swimmers))
            for i, swimmer in enumerate(relay_swimmers):
                name, year, leg = swimmer[0], swimmer[1], swimmer[2]
                leg_time = self.format_time(self.leg_times[i]) if i < len(self.leg_times) and self.leg_times[i] else ""
                checkbox_item = QTableWidgetItem()
                checkbox_item.setCheckState(Qt.Unchecked)
                self.table.setItem(i, 0, checkbox_item)
                self.table.setItem(i, 1, QTableWidgetItem(str(leg)))
                self.table.setItem(i, 2, QTableWidgetItem(name))
                self.table.setItem(i, 3, QTableWidgetItem(year or ''))
                self.table.setItem(i, 4, QTableWidgetItem(leg_time))

            self.table.setColumnWidth(0, 30)
            self.table.setColumnWidth(1, 40)
            self.table.setColumnWidth(3, 50)
            self.table.setColumnWidth(4, 100)

        layout.addWidget(self.table)

        # Buttons
        btn_layout = QHBoxLayout()

        if not self.read_only:
            select_all_btn = QPushButton("Select All")
            select_all_btn.clicked.connect(self.select_all)
            btn_layout.addWidget(select_all_btn)

            save_btn = QPushButton("Save Selected as Individual Swims")
            save_btn.clicked.connect(self.save_selected_legs)
            btn_layout.addWidget(save_btn)

        btn_layout.addStretch()

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.close)
        btn_layout.addWidget(close_btn)

        layout.addLayout(btn_layout)

    def on_cell_clicked(self, row, col):
        if col == 0:
            item = self.table.item(row, 0)
            if item.checkState() == Qt.Checked:
                item.setCheckState(Qt.Unchecked)
            else:
                item.setCheckState(Qt.Checked)

    def select_all(self):
        for i in range(self.table.rowCount()):
            self.table.item(i, 0).setCheckState(Qt.Checked)

    def calculate_leg_times(self, splits, num_swimmers, event_distance):
        """
        Calculate individual leg times from relay splits.

        Splits may be diff-based (from parenthesized values) or cumulative.
        Auto-detects format: if monotonically increasing → cumulative,
        otherwise → diff/split values.

        For diff splits (e.g. 4x100):
          [22.46, 46.96, 24.65, 53.75, 21.31, 45.85, 20.37, 43.05]
          Leg times are at every splits_per_leg-th index: indices 1,3,5,7
          These ARE the leg times directly.

        For cumulative splits:
          [22.46, 46.96, 71.61, 100.71, 122.02, 146.56, 166.93, 189.61]
          Leg times = cumulative[end] - cumulative[prev_end].
        """
        if not splits or not num_swimmers:
            return []

        leg_distance = event_distance // num_swimmers if num_swimmers else 50
        splits_per_leg = leg_distance // 50
        if splits_per_leg == 0:
            return []

        # Auto-detect: monotonically increasing → cumulative
        is_cumulative = (len(splits) > 1 and
                         all(splits[i] <= splits[i + 1] for i in range(len(splits) - 1)))

        leg_times = []
        prev_cumulative = 0.0
        for i in range(num_swimmers):
            end_idx = (i + 1) * splits_per_leg - 1

            if end_idx < len(splits):
                if is_cumulative:
                    cumulative = splits[end_idx]
                    leg_time = round(cumulative - prev_cumulative, 2)
                    prev_cumulative = cumulative
                else:
                    # Diff splits: value at end_idx IS the leg time
                    leg_time = round(splits[end_idx], 2)
                leg_times.append(leg_time)
            else:
                leg_times.append(None)

        return leg_times

    def format_time(self, seconds):
        if seconds is None:
            return ""
        if seconds >= 60:
            mins = int(seconds // 60)
            secs = seconds % 60
            return f"{mins}:{secs:05.2f}"
        return f"{seconds:.2f}"

    def save_selected_legs(self):
        selected = []
        for i in range(self.table.rowCount()):
            if self.table.item(i, 0).checkState() == Qt.Checked:
                selected.append(i)

        if not selected:
            QMessageBox.information(self, "Info", "No legs selected.")
            return

        # Determine strokes
        if 'Medley' in self.row_data['event_name']:
            strokes = ['Backstroke', 'Breaststroke', 'Butterfly', 'Freestyle']
        else:
            strokes = ['Freestyle'] * 4

        saved_count = 0
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # Get meet info for the copy
        cursor.execute('SELECT meet_name, meet_date, filename FROM meets WHERE id = ?',
                       (self.row_data['meet_id'],))
        meet = cursor.fetchone()
        meet_name = meet['meet_name'] if meet else ''
        meet_date = meet['meet_date'] if meet else ''
        meet_filename = meet['filename'] if meet else ''

        for i in selected:
            if i >= len(self.relay_swimmers):
                continue

            s = self.relay_swimmers[i]
            name, year, leg = s[0], s[1], s[2]
            leg_time = self.leg_times[i] if i < len(self.leg_times) else None
            if not leg_time:
                continue

            leg_stroke = strokes[i] if i < len(strokes) else 'Freestyle'
            leg_type = "lead-off" if leg == 1 else "relay"
            leg_event = f"50 {leg_stroke} ({leg_type})"
            time_str = self.format_time(leg_time)

            try:
                cursor.execute('''
                    INSERT OR IGNORE INTO saved_results
                    (place, name, year, team, event_name, event_gender, event_distance,
                     finals_time, finals_seconds, points, time_standard,
                     is_relay, is_diving, is_exhibition, is_dq, is_scratch,
                     round, reaction_time, dq_reason, splits, relay_swimmers,
                     meet_name, meet_date, meet_filename)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ''', (
                    None, name, year, self.row_data['team'], leg_event,
                    self.row_data['event_gender'], 50, time_str, leg_time, None, None,
                    0, 0, 0, 0, 0, None, None, None, '[]', '[]',
                    meet_name, meet_date, meet_filename,
                ))
                if cursor.rowcount > 0:
                    saved_count += 1
            except Exception:
                pass

        conn.commit()
        conn.close()

        QMessageBox.information(self, "Saved", f"Saved {saved_count} relay leg(s) as individual swims.")
        self.accept()


class MeetResultsApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("HY-TEK Meet Results Viewer")
        self.setMinimumSize(1300, 750)

        self.current_meet_id = None
        self.selected_ids = set()
        self.meets_data = {}
        self.all_results = []
        self.search_timer = QTimer()
        self.search_timer.setSingleShot(True)
        self.search_timer.timeout.connect(self.apply_filters)

        self.sort_column = 0
        self.sort_order = Qt.AscendingOrder

        self.init_db()
        self.setup_ui()
        self.refresh_meets_list()

    def get_db(self):
        DB_DIR.mkdir(exist_ok=True)
        conn = sqlite3.connect(str(DB_PATH))
        conn.row_factory = sqlite3.Row
        return conn

    def init_db(self):
        conn = self.get_db()
        cursor = conn.cursor()

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS meets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                filename TEXT NOT NULL,
                upload_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                meet_name TEXT,
                meet_date TEXT
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                meet_id INTEGER NOT NULL,
                place REAL,
                name TEXT,
                year TEXT,
                team TEXT,
                event_name TEXT,
                event_gender TEXT,
                event_distance INTEGER,
                finals_time TEXT,
                finals_seconds REAL,
                points REAL,
                time_standard TEXT,
                is_relay INTEGER,
                is_diving INTEGER,
                is_exhibition INTEGER,
                is_dq INTEGER,
                is_scratch INTEGER,
                round TEXT,
                reaction_time REAL,
                dq_reason TEXT,
                splits TEXT,
                relay_swimmers TEXT,
                FOREIGN KEY (meet_id) REFERENCES meets(id)
            )
        ''')

        # Migration: add new columns to existing databases
        for col in ['round TEXT', 'reaction_time REAL']:
            try:
                cursor.execute(f'ALTER TABLE results ADD COLUMN {col}')
            except sqlite3.OperationalError:
                pass  # Column already exists

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS saved_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                place REAL,
                name TEXT,
                year TEXT,
                team TEXT,
                event_name TEXT,
                event_gender TEXT,
                event_distance INTEGER,
                finals_time TEXT,
                finals_seconds REAL,
                points REAL,
                time_standard TEXT,
                is_relay INTEGER,
                is_diving INTEGER,
                is_exhibition INTEGER,
                is_dq INTEGER,
                is_scratch INTEGER,
                round TEXT,
                reaction_time REAL,
                dq_reason TEXT,
                splits TEXT,
                relay_swimmers TEXT,
                meet_name TEXT,
                meet_date TEXT,
                meet_filename TEXT,
                saved_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(name, event_name, finals_time, round, meet_name)
            )
        ''')

        # Migration: if old saved_results has result_id column, migrate data to new schema
        cursor.execute("PRAGMA table_info(saved_results)")
        columns = {col['name'] for col in cursor.fetchall()}
        if 'result_id' in columns and 'event_name' not in columns:
            # Old schema — migrate to new
            cursor.execute('''
                SELECT r.*, m.meet_name, m.meet_date, m.filename
                FROM saved_results s
                JOIN results r ON s.result_id = r.id
                JOIN meets m ON r.meet_id = m.id
            ''')
            old_saved = cursor.fetchall()
            cursor.execute('DROP TABLE saved_results')
            cursor.execute('''
                CREATE TABLE saved_results (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    place REAL, name TEXT, year TEXT, team TEXT,
                    event_name TEXT, event_gender TEXT, event_distance INTEGER,
                    finals_time TEXT, finals_seconds REAL, points REAL,
                    time_standard TEXT, is_relay INTEGER, is_diving INTEGER,
                    is_exhibition INTEGER, is_dq INTEGER, is_scratch INTEGER,
                    round TEXT, reaction_time REAL, dq_reason TEXT,
                    splits TEXT, relay_swimmers TEXT,
                    meet_name TEXT, meet_date TEXT, meet_filename TEXT,
                    saved_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(name, event_name, finals_time, round, meet_name)
                )
            ''')
            for row in old_saved:
                try:
                    cursor.execute('''
                        INSERT OR IGNORE INTO saved_results
                        (place, name, year, team, event_name, event_gender, event_distance,
                         finals_time, finals_seconds, points, time_standard,
                         is_relay, is_diving, is_exhibition, is_dq, is_scratch,
                         round, reaction_time, dq_reason, splits, relay_swimmers,
                         meet_name, meet_date, meet_filename)
                        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    ''', (
                        row['place'], row['name'], row['year'], row['team'],
                        row['event_name'], row['event_gender'], row['event_distance'],
                        row['finals_time'], row['finals_seconds'], row['points'],
                        row['time_standard'], row['is_relay'], row['is_diving'],
                        row['is_exhibition'], row['is_dq'], row['is_scratch'],
                        row['round'], row['reaction_time'], row['dq_reason'],
                        row['splits'], row['relay_swimmers'],
                        row['meet_name'], row['meet_date'], row['filename'],
                    ))
                except Exception:
                    pass

        cursor.execute('CREATE INDEX IF NOT EXISTS idx_meet ON results(meet_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_team ON results(team)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_name ON results(name)')

        # Prevent duplicate results (same swimmer, event, time, round at same meet)
        # Drop old index without round (migration)
        cursor.execute('DROP INDEX IF EXISTS idx_no_dup')
        cursor.execute('CREATE UNIQUE INDEX IF NOT EXISTS idx_no_dup ON results(meet_id, name, event_name, finals_time, round)')

        # Migrate existing dates to ISO format
        cursor.execute('SELECT id, meet_date FROM meets WHERE meet_date IS NOT NULL')
        for row in cursor.fetchall():
            iso = normalize_date(row['meet_date'])
            if iso != row['meet_date']:
                cursor.execute('UPDATE meets SET meet_date = ? WHERE id = ?', (iso, row['id']))

        conn.commit()
        conn.close()

    def setup_ui(self):
        # Menu bar
        menubar = self.menuBar()
        file_menu = menubar.addMenu("File")

        open_action = QAction("Open PDF...", self)
        open_action.setShortcut(QKeySequence.Open)
        open_action.triggered.connect(self.load_pdf)
        file_menu.addAction(open_action)

        export_action = QAction("Export CSV...", self)
        export_action.setShortcut(QKeySequence("Ctrl+E"))
        export_action.triggered.connect(self.export_csv)
        file_menu.addAction(export_action)

        file_menu.addSeparator()

        exit_action = QAction("Exit", self)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        # Central widget
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(10, 10, 10, 10)

        # Tab widget
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)

        # Meets tab
        meets_widget = QWidget()
        self.tabs.addTab(meets_widget, "Meet Results")
        self.setup_meets_tab(meets_widget)

        # Saved tab
        saved_widget = QWidget()
        self.tabs.addTab(saved_widget, "Saved Results")
        self.setup_saved_tab(saved_widget)

        # Best Relay tab
        relay_widget = QWidget()
        self.tabs.addTab(relay_widget, "Best Relay")
        self.setup_best_relay_tab(relay_widget)

        self.tabs.currentChanged.connect(self.on_tab_changed)

        # Status bar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Ready - Upload a PDF to get started")

    def setup_meets_tab(self, parent):
        layout = QVBoxLayout(parent)

        # Top row: meet selector
        top_layout = QHBoxLayout()
        top_layout.addWidget(QLabel("Meet:"))

        self.meet_combo = QComboBox()
        self.meet_combo.setMinimumWidth(400)
        self.meet_combo.currentIndexChanged.connect(self.on_meet_selected)
        top_layout.addWidget(self.meet_combo)

        upload_btn = QPushButton("Upload PDF...")
        upload_btn.clicked.connect(self.load_pdf)
        top_layout.addWidget(upload_btn)

        delete_btn = QPushButton("Delete Meet")
        delete_btn.clicked.connect(self.delete_current_meet)
        top_layout.addWidget(delete_btn)

        top_layout.addStretch()
        layout.addLayout(top_layout)

        # Filters
        filter_group = QGroupBox("Filters")
        filter_layout = QHBoxLayout(filter_group)

        filter_layout.addWidget(QLabel("Search:"))
        self.search_edit = QLineEdit()
        self.search_edit.setMaximumWidth(150)
        self.search_edit.textChanged.connect(self.debounced_search)
        filter_layout.addWidget(self.search_edit)

        filter_layout.addWidget(QLabel("Team:"))
        self.team_combo = QComboBox()
        self.team_combo.setMinimumWidth(100)
        self.team_combo.currentIndexChanged.connect(self.apply_filters)
        filter_layout.addWidget(self.team_combo)

        filter_layout.addWidget(QLabel("Event:"))
        self.event_combo = QComboBox()
        self.event_combo.setMaximumWidth(120)
        self.event_combo.currentIndexChanged.connect(self.apply_filters)
        filter_layout.addWidget(self.event_combo)

        filter_layout.addSpacing(10)
        filter_layout.addWidget(QLabel("Stroke:"))
        self.stroke_combo = QComboBox()
        self.stroke_combo.addItems(["All", "Freestyle", "Backstroke", "Breaststroke", "Butterfly", "IM"])
        self.stroke_combo.currentIndexChanged.connect(self.apply_filters)
        filter_layout.addWidget(self.stroke_combo)

        filter_layout.addSpacing(10)
        filter_layout.addWidget(QLabel("Distance:"))
        self.distance_combo = QComboBox()
        self.distance_combo.setMinimumWidth(70)
        self.distance_combo.currentIndexChanged.connect(self.apply_filters)
        filter_layout.addWidget(self.distance_combo)

        filter_layout.addWidget(QLabel("Gender:"))
        self.gender_combo = QComboBox()
        self.gender_combo.addItems(["All", "Women", "Men"])
        self.gender_combo.currentIndexChanged.connect(self.apply_filters)
        filter_layout.addWidget(self.gender_combo)

        filter_layout.addWidget(QLabel("Round:"))
        self.round_combo = QComboBox()
        self.round_combo.addItem("All")
        self.round_combo.currentIndexChanged.connect(self.apply_filters)
        filter_layout.addWidget(self.round_combo)

        self.show_exh_check = QCheckBox("Exhibition")
        self.show_exh_check.setChecked(True)
        self.show_exh_check.stateChanged.connect(self.apply_filters)
        filter_layout.addWidget(self.show_exh_check)

        self.show_dq_check = QCheckBox("DQ/SCR")
        self.show_dq_check.setChecked(True)
        self.show_dq_check.stateChanged.connect(self.apply_filters)
        filter_layout.addWidget(self.show_dq_check)

        clear_btn = QPushButton("Clear")
        clear_btn.clicked.connect(self.clear_filters)
        filter_layout.addWidget(clear_btn)

        filter_layout.addStretch()
        layout.addWidget(filter_group)

        # Selection actions
        sel_layout = QHBoxLayout()
        self.selection_label = QLabel("0 selected")
        sel_layout.addWidget(self.selection_label)

        save_sel_btn = QPushButton("Save Selected")
        save_sel_btn.clicked.connect(self.save_selected)
        sel_layout.addWidget(save_sel_btn)

        clear_sel_btn = QPushButton("Clear Selection")
        clear_sel_btn.clicked.connect(self.clear_selection)
        sel_layout.addWidget(clear_sel_btn)

        select_all_btn = QPushButton("Select All Visible")
        select_all_btn.clicked.connect(self.select_all_visible)
        sel_layout.addWidget(select_all_btn)

        sel_layout.addStretch()
        layout.addLayout(sel_layout)

        # Results table
        self.results_table = QTableWidget()
        self.results_table.setColumnCount(10)
        self.results_table.setHorizontalHeaderLabels(['', 'Place', 'Name', 'Year', 'Team', 'Event', 'Time', 'Pts', 'Round', 'Status'])
        # Use Interactive mode for all columns, stretch last section to fill
        self.results_table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.results_table.horizontalHeader().setStretchLastSection(True)
        self.results_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.results_table.setAlternatingRowColors(True)
        self.results_table.cellClicked.connect(self.on_results_cell_clicked)
        self.results_table.cellDoubleClicked.connect(self.on_results_double_clicked)
        self.results_table.horizontalHeader().sectionClicked.connect(self.on_header_clicked)

        self.results_table.setColumnWidth(0, 30)
        self.results_table.setColumnWidth(1, 50)
        self.results_table.setColumnWidth(2, 180)  # Name
        self.results_table.setColumnWidth(3, 45)
        self.results_table.setColumnWidth(4, 80)
        self.results_table.setColumnWidth(5, 200)  # Event
        self.results_table.setColumnWidth(6, 90)
        self.results_table.setColumnWidth(7, 50)
        self.results_table.setColumnWidth(8, 70)   # Round

        layout.addWidget(self.results_table)

    def setup_saved_tab(self, parent):
        layout = QVBoxLayout(parent)

        # Top row
        top_layout = QHBoxLayout()
        self.saved_count_label = QLabel("0 saved results")
        top_layout.addWidget(self.saved_count_label)

        top_layout.addStretch()

        export_btn = QPushButton("Export Saved...")
        export_btn.clicked.connect(self.export_saved)
        top_layout.addWidget(export_btn)

        remove_btn = QPushButton("Remove Selected")
        remove_btn.clicked.connect(self.remove_saved_selected)
        top_layout.addWidget(remove_btn)

        layout.addLayout(top_layout)

        # Filters for saved results
        filter_group = QGroupBox("Filters")
        filter_layout = QHBoxLayout(filter_group)

        filter_layout.addWidget(QLabel("Search:"))
        self.saved_search_edit = QLineEdit()
        self.saved_search_edit.setMaximumWidth(150)
        self.saved_search_edit.textChanged.connect(self.debounced_saved_search)
        filter_layout.addWidget(self.saved_search_edit)

        filter_layout.addWidget(QLabel("Team:"))
        self.saved_team_combo = QComboBox()
        self.saved_team_combo.setMinimumWidth(100)
        self.saved_team_combo.currentIndexChanged.connect(self.apply_saved_filters)
        filter_layout.addWidget(self.saved_team_combo)

        filter_layout.addWidget(QLabel("Event:"))
        self.saved_event_combo = QComboBox()
        self.saved_event_combo.setMinimumWidth(150)
        self.saved_event_combo.currentIndexChanged.connect(self.apply_saved_filters)
        filter_layout.addWidget(self.saved_event_combo)

        filter_layout.addSpacing(10)
        filter_layout.addWidget(QLabel("Stroke:"))
        self.saved_stroke_combo = QComboBox()
        self.saved_stroke_combo.addItems(["All", "Freestyle", "Backstroke", "Breaststroke", "Butterfly", "IM"])
        self.saved_stroke_combo.currentIndexChanged.connect(self.apply_saved_filters)
        filter_layout.addWidget(self.saved_stroke_combo)

        filter_layout.addSpacing(10)
        filter_layout.addWidget(QLabel("Distance:"))
        self.saved_distance_combo = QComboBox()
        self.saved_distance_combo.setMinimumWidth(70)
        self.saved_distance_combo.currentIndexChanged.connect(self.apply_saved_filters)
        filter_layout.addWidget(self.saved_distance_combo)

        filter_layout.addWidget(QLabel("Meet:"))
        self.saved_meet_combo = QComboBox()
        self.saved_meet_combo.setMinimumWidth(150)
        self.saved_meet_combo.currentIndexChanged.connect(self.apply_saved_filters)
        filter_layout.addWidget(self.saved_meet_combo)

        filter_layout.addWidget(QLabel("Gender:"))
        self.saved_gender_combo = QComboBox()
        self.saved_gender_combo.addItems(["All", "Women", "Men"])
        self.saved_gender_combo.currentIndexChanged.connect(self.apply_saved_filters)
        filter_layout.addWidget(self.saved_gender_combo)

        clear_btn = QPushButton("Clear")
        clear_btn.clicked.connect(self.clear_saved_filters)
        filter_layout.addWidget(clear_btn)

        filter_layout.addStretch()
        layout.addWidget(filter_group)

        # Saved results table - removed Place and Points columns
        self.saved_table = QTableWidget()
        self.saved_table.setColumnCount(7)
        self.saved_table.setHorizontalHeaderLabels(['Name', 'Year', 'Team', 'Event', 'Time', 'Meet', 'Date'])
        # Use Interactive mode for all columns, stretch last section to fill
        self.saved_table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.saved_table.horizontalHeader().setStretchLastSection(True)
        self.saved_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.saved_table.setAlternatingRowColors(True)
        self.saved_table.cellDoubleClicked.connect(self.on_saved_double_clicked)

        # Set default column widths
        self.saved_table.setColumnWidth(0, 150)  # Name
        self.saved_table.setColumnWidth(1, 40)   # Year
        self.saved_table.setColumnWidth(2, 80)   # Team
        self.saved_table.setColumnWidth(3, 160)  # Event
        self.saved_table.setColumnWidth(4, 70)   # Time
        self.saved_table.setColumnWidth(5, 150)  # Meet

        layout.addWidget(self.saved_table)

        # Timer for debounced search
        self.saved_search_timer = QTimer()
        self.saved_search_timer.setSingleShot(True)
        self.saved_search_timer.timeout.connect(self.apply_saved_filters)

    def setup_best_relay_tab(self, parent):
        layout = QVBoxLayout(parent)

        # Header
        header_layout = QHBoxLayout()
        header_layout.addWidget(QLabel("<b>Best Relay Calculator</b>"))

        # Team filter
        header_layout.addWidget(QLabel("Team:"))
        self.relay_team_combo = QComboBox()
        self.relay_team_combo.currentIndexChanged.connect(self.compute_best_relays)
        header_layout.addWidget(self.relay_team_combo)

        refresh_btn = QPushButton("Refresh")
        refresh_btn.clicked.connect(self.compute_best_relays)
        header_layout.addWidget(refresh_btn)

        header_layout.addStretch()
        layout.addLayout(header_layout)

        # Date range filter
        date_layout = QHBoxLayout()
        date_layout.addWidget(QLabel("Date Range:"))

        self.relay_use_dates = QCheckBox("Filter by date")
        self.relay_use_dates.setChecked(False)
        self.relay_use_dates.stateChanged.connect(self.on_relay_date_toggle)
        date_layout.addWidget(self.relay_use_dates)

        date_layout.addWidget(QLabel("From:"))
        self.relay_date_from = QDateEdit()
        self.relay_date_from.setCalendarPopup(True)
        self.relay_date_from.setDisplayFormat("M/d/yyyy")
        self.relay_date_from.setDate(QDate.currentDate().addYears(-1))
        self.relay_date_from.setEnabled(False)
        self.relay_date_from.dateChanged.connect(self.compute_best_relays)
        date_layout.addWidget(self.relay_date_from)

        date_layout.addWidget(QLabel("To:"))
        self.relay_date_to = QDateEdit()
        self.relay_date_to.setCalendarPopup(True)
        self.relay_date_to.setDisplayFormat("M/d/yyyy")
        self.relay_date_to.setDate(QDate.currentDate())
        self.relay_date_to.setEnabled(False)
        self.relay_date_to.dateChanged.connect(self.compute_best_relays)
        date_layout.addWidget(self.relay_date_to)

        date_layout.addStretch()
        layout.addLayout(date_layout)

        # Relay results area - use a scroll area
        from PySide6.QtWidgets import QScrollArea, QFrame

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)

        self.relay_container = QWidget()
        self.relay_layout = QVBoxLayout(self.relay_container)
        self.relay_layout.setSpacing(10)

        scroll.setWidget(self.relay_container)
        layout.addWidget(scroll)

    def on_relay_date_toggle(self, state):
        """Enable/disable date range pickers"""
        enabled = state == Qt.Checked.value if hasattr(Qt.Checked, 'value') else bool(state)
        self.relay_date_from.setEnabled(enabled)
        self.relay_date_to.setEnabled(enabled)
        self.compute_best_relays()

    def compute_best_relays(self):
        """Compute optimal relay lineups from saved results for both genders"""
        from PySide6.QtWidgets import QFrame, QGridLayout

        # Clear previous results
        while self.relay_layout.count():
            child = self.relay_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        team = self.relay_team_combo.currentText() if self.relay_team_combo.currentIndex() > 0 else None

        # Get results for both genders
        conn = self.get_db()
        cursor = conn.cursor()

        results_by_gender = {}
        for gender in ["Women", "Men"]:
            query = '''
                SELECT * FROM saved_results
                WHERE event_gender = ? AND is_relay = 0 AND is_dq = 0 AND is_scratch = 0
            '''
            params = [gender]
            if team:
                query += ' AND team = ?'
                params.append(team)

            # Date range filter
            if self.relay_use_dates.isChecked():
                date_from = self.relay_date_from.date().toString("yyyy-MM-dd")
                date_to = self.relay_date_to.date().toString("yyyy-MM-dd")
                query += ' AND meet_date >= ? AND meet_date <= ?'
                params.extend([date_from, date_to])

            cursor.execute(query, params)
            results_by_gender[gender] = [dict(row) for row in cursor.fetchall()]

        conn.close()

        if not results_by_gender["Women"] and not results_by_gender["Men"]:
            label = QLabel("No saved results found. Save some results first.")
            label.setStyleSheet("color: gray; padding: 20px;")
            self.relay_layout.addWidget(label)
            self.relay_layout.addStretch()
            return

        # Parse swimmer times for each gender
        swimmer_times_by_gender = {
            "Women": self.parse_swimmer_times(results_by_gender["Women"]),
            "Men": self.parse_swimmer_times(results_by_gender["Men"])
        }

        # Relay configurations
        relay_configs = [
            ("200 FR", 50, ["Freestyle"], False),
            ("400 FR", 100, ["Freestyle"], False),
            ("800 FR", 200, ["Freestyle"], False),
            ("200 Medley", 50, ["Backstroke", "Breaststroke", "Butterfly", "Freestyle"], True),
            ("400 Medley", 100, ["Backstroke", "Breaststroke", "Butterfly", "Freestyle"], True),
        ]

        # Create side-by-side layout for each relay
        for relay_name, distance, strokes, is_medley in relay_configs:
            women_result = self.compute_single_relay(swimmer_times_by_gender["Women"], distance, strokes, is_medley)
            men_result = self.compute_single_relay(swimmer_times_by_gender["Men"], distance, strokes, is_medley)
            self.add_relay_row(relay_name, women_result, men_result, strokes, is_medley)

        self.relay_layout.addStretch()

    def parse_swimmer_times(self, results):
        """
        Parse results into a dictionary of swimmer times.
        Returns: {swimmer_name: {(distance, stroke): [(time, is_leadoff_eligible, source, meet_name), ...]}}

        - Individual event times are leadoff eligible
        - Relay lead-off splits are leadoff eligible
        - Relay non-leadoff splits are NOT leadoff eligible
        - First 50 splits from 100-yard individual/lead-off events are added as (50, stroke) candidates
        """
        swimmer_times = {}

        for r in results:
            event_name = r['event_name'] or ''
            distance = r['event_distance'] or 0
            time_seconds = r['finals_seconds']
            name = r['name'] or ''
            meet_name = r.get('meet_name', '') or ''

            if not name or not time_seconds or time_seconds <= 0:
                continue

            # Determine stroke from event name
            stroke = self.extract_stroke(event_name)
            if not stroke:
                continue

            # Check if this is a relay split
            is_relay_split = '(relay)' in event_name.lower() or '(lead-off)' in event_name.lower()
            is_leadoff = '(lead-off)' in event_name.lower()

            # Leadoff eligible: individual times or lead-off relay splits
            is_leadoff_eligible = not is_relay_split or is_leadoff

            source = "lead-off" if is_leadoff else ("relay" if is_relay_split else "individual")

            if name not in swimmer_times:
                swimmer_times[name] = {}

            key = (distance, stroke)
            if key not in swimmer_times[name]:
                swimmer_times[name][key] = []

            swimmer_times[name][key].append((time_seconds, is_leadoff_eligible, source, meet_name))

            # Extract first 50 split from 100-yard individual/lead-off events
            if distance == 100 and is_leadoff_eligible:
                splits_raw = r.get('splits')
                if splits_raw:
                    try:
                        splits = json.loads(splits_raw) if isinstance(splits_raw, str) else splits_raw
                    except (json.JSONDecodeError, TypeError):
                        splits = None
                    if splits and len(splits) >= 1:
                        first_50 = splits[0]
                        if isinstance(first_50, (int, float)) and 15 <= first_50 <= 40:
                            split_key = (50, stroke)
                            if split_key not in swimmer_times[name]:
                                swimmer_times[name][split_key] = []
                            split_source = f"50 split ({source})"
                            swimmer_times[name][split_key].append(
                                (first_50, is_leadoff_eligible, split_source, meet_name))

        return swimmer_times

    def extract_stroke(self, event_name):
        """Extract stroke from event name"""
        event_lower = event_name.lower()
        if 'free' in event_lower:
            return 'Freestyle'
        elif 'back' in event_lower:
            return 'Backstroke'
        elif 'breast' in event_lower:
            return 'Breaststroke'
        elif 'fly' in event_lower or 'butter' in event_lower:
            return 'Butterfly'
        elif 'im' in event_lower or 'medley' in event_lower:
            # Individual medley - not usable for relay legs
            return None
        return None

    def compute_single_relay(self, swimmer_times, distance, strokes, is_medley):
        """
        Compute optimal relay lineup using exhaustive search over top candidates.
        Handles swimmers who are competitive in multiple strokes by finding the
        assignment that minimises total relay time.
        Returns: [(swimmer_name, stroke, time, source, meet_name), ...]
        """
        # Build candidate lists per leg (top 8 per leg is enough; 8^4 = 4096 max combos)
        # Each candidate: (swimmer, time, source, meet_name)
        leg_candidates = []
        for leg_idx, stroke in enumerate(strokes if is_medley else ['Freestyle'] * 4):
            is_leadoff = (leg_idx == 0)
            key = (distance, stroke)
            candidates = []
            for swimmer, times_dict in swimmer_times.items():
                if key not in times_dict:
                    continue
                best_time = None
                best_source = None
                best_meet = None
                for time, leadoff_eligible, source, meet_name in times_dict[key]:
                    if is_leadoff and not leadoff_eligible:
                        continue
                    if best_time is None or time < best_time:
                        best_time = time
                        best_source = source
                        best_meet = meet_name
                if best_time is not None:
                    candidates.append((swimmer, best_time, best_source, best_meet))
            candidates.sort(key=lambda x: x[1])
            leg_candidates.append(candidates[:8])

        # For free relays (all same stroke), just pick top 4 distinct swimmers
        if not is_medley:
            seen = set()
            relay = []
            # Leg 0 needs leadoff-eligible
            for c in leg_candidates[0]:
                if c[0] not in seen:
                    relay.append((c[0], 'Freestyle', c[1], c[2], c[3]))
                    seen.add(c[0])
                    break
            # Fill remaining legs from all candidates (re-derive with any time)
            key = (distance, 'Freestyle')
            all_candidates = []
            for swimmer, times_dict in swimmer_times.items():
                if swimmer in seen or key not in times_dict:
                    continue
                best_time = None
                best_source = None
                best_meet = None
                for t, _, s, mn in times_dict[key]:
                    if best_time is None or t < best_time:
                        best_time = t
                        best_source = s
                        best_meet = mn
                if best_time is not None:
                    all_candidates.append((swimmer, best_time, best_source, best_meet))
            all_candidates.sort(key=lambda x: x[1])
            for c in all_candidates:
                if len(relay) >= 4:
                    break
                relay.append((c[0], 'Freestyle', c[1], c[2], c[3]))
            while len(relay) < 4:
                relay.append((None, 'Freestyle', None, None, None))
            return relay

        # Medley relay: exhaustive search over top candidates per leg
        best_total = float('inf')
        best_assignment = None

        for c0 in leg_candidates[0]:
            for c1 in leg_candidates[1]:
                if c1[0] == c0[0]:
                    continue
                t01 = c0[1] + c1[1]
                if t01 >= best_total:
                    continue  # prune
                for c2 in leg_candidates[2]:
                    if c2[0] in (c0[0], c1[0]):
                        continue
                    t012 = t01 + c2[1]
                    if t012 >= best_total:
                        continue  # prune
                    for c3 in leg_candidates[3]:
                        if c3[0] in (c0[0], c1[0], c2[0]):
                            continue
                        total = t012 + c3[1]
                        if total < best_total:
                            best_total = total
                            best_assignment = [c0, c1, c2, c3]

        if best_assignment is None:
            # Not enough swimmers — fill what we can
            relay = []
            used = set()
            for leg_idx, stroke in enumerate(strokes):
                placed = False
                for c in leg_candidates[leg_idx]:
                    if c[0] not in used:
                        relay.append((c[0], stroke, c[1], c[2], c[3]))
                        used.add(c[0])
                        placed = True
                        break
                if not placed:
                    relay.append((None, stroke, None, None, None))
            return relay

        return [(c[0], stroke, c[1], c[2], c[3])
                for c, stroke in zip(best_assignment, strokes)]

    def add_relay_row(self, relay_name, women_result, men_result, strokes, is_medley):
        """Add a relay row with Women on left, Men on right"""
        from PySide6.QtWidgets import QFrame, QGridLayout

        card = QFrame()
        card.setFrameShape(QFrame.StyledPanel)
        card.setStyleSheet("""
            QFrame {
                border: 1px solid palette(mid);
                border-radius: 6px;
                padding: 8px;
                background-color: palette(base);
            }
        """)

        main_layout = QHBoxLayout(card)
        main_layout.setSpacing(20)

        # Relay name in center/title area
        title = QLabel(f"<b>{relay_name}</b>")
        title.setStyleSheet("font-size: 13px;")

        # Women side (left)
        women_widget = self.create_gender_relay_widget("Women", women_result, strokes, is_medley)

        # Men side (right)
        men_widget = self.create_gender_relay_widget("Men", men_result, strokes, is_medley)

        # Layout: Women | Title | Men
        main_layout.addWidget(women_widget, 1)

        # Center title
        center_layout = QVBoxLayout()
        center_layout.addStretch()
        center_layout.addWidget(title)
        center_layout.addStretch()
        main_layout.addLayout(center_layout)

        main_layout.addWidget(men_widget, 1)

        self.relay_layout.addWidget(card)

    def create_gender_relay_widget(self, gender, relay_result, strokes, is_medley):
        """Create a compact relay widget for one gender"""
        from PySide6.QtWidgets import QFrame, QGridLayout

        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        # Header with gender and total time
        total_time = sum(r[2] for r in relay_result if r[2] is not None)
        complete = all(r[0] is not None for r in relay_result)

        if complete:
            header = QLabel(f"<b>{gender}</b> - {self.format_time(total_time)}")
        else:
            header = QLabel(f"<b>{gender}</b> - <i>incomplete</i>")
        layout.addWidget(header)

        # Compact grid: Leg | Swimmer | Time
        grid = QGridLayout()
        grid.setSpacing(2)
        grid.setContentsMargins(0, 0, 0, 0)

        for row, (swimmer, stroke, time, source, meet_name) in enumerate(relay_result):
            # Leg number
            leg_label = QLabel(f"{row + 1}.")
            leg_label.setMinimumWidth(25)
            leg_label.setMaximumWidth(30)
            grid.addWidget(leg_label, row, 0)

            if swimmer:
                # Swimmer name (truncate if too long)
                name = swimmer if len(swimmer) <= 20 else swimmer[:18] + "..."
                name_label = QLabel(name)
                grid.addWidget(name_label, row, 1)

                # Time with source indicator
                time_str = self.format_time(time)
                if source == "relay":
                    time_str += " (r)"
                elif source == "lead-off":
                    time_str += " (l)"
                time_label = QLabel(time_str)
                time_label.setAlignment(Qt.AlignRight)
                grid.addWidget(time_label, row, 2)

                # Meet name
                meet_short = (meet_name or '')[:25]
                meet_label = QLabel(meet_short)
                meet_label.setStyleSheet("color: gray; font-size: 11px;")
                grid.addWidget(meet_label, row, 3)
            else:
                empty = QLabel("—")
                empty.setStyleSheet("color: palette(mid);")
                grid.addWidget(empty, row, 1)
                grid.addWidget(QLabel(""), row, 2)
                grid.addWidget(QLabel(""), row, 3)

        layout.addLayout(grid)
        return widget

    def format_time(self, seconds):
        """Format seconds as MM:SS.ss or SS.ss"""
        if seconds is None:
            return ""
        if seconds >= 60:
            mins = int(seconds // 60)
            secs = seconds % 60
            return f"{mins}:{secs:05.2f}"
        return f"{seconds:.2f}"

    def load_relay_teams(self):
        """Load teams for the relay team filter"""
        conn = self.get_db()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT DISTINCT team FROM saved_results
            WHERE team != "" ORDER BY team
        ''')
        teams = [row['team'] for row in cursor.fetchall()]
        conn.close()

        self.relay_team_combo.blockSignals(True)
        self.relay_team_combo.clear()
        self.relay_team_combo.addItem("All Teams")
        for team in teams:
            self.relay_team_combo.addItem(team)
        self.relay_team_combo.blockSignals(False)

    def refresh_meets_list(self):
        conn = self.get_db()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT m.id, m.meet_name, m.meet_date, m.filename, COUNT(r.id) as cnt
            FROM meets m LEFT JOIN results r ON r.meet_id = m.id
            GROUP BY m.id ORDER BY m.meet_date DESC, m.upload_date DESC
        ''')
        meets = cursor.fetchall()
        conn.close()

        self.meet_combo.blockSignals(True)
        self.meet_combo.clear()
        self.meet_combo.addItem("All Meets")

        self.meets_data = {}
        for m in meets:
            label = f"{m['meet_name'] or m['filename']} ({m['meet_date'] or 'No date'}) - {m['cnt']} results"
            self.meets_data[label] = m['id']
            self.meet_combo.addItem(label)

        self.meet_combo.blockSignals(False)

        if meets and not self.current_meet_id:
            self.meet_combo.setCurrentIndex(1)
            self.current_meet_id = meets[0]['id']
            self.load_meet_results()

    def on_meet_selected(self, index):
        if index == 0:
            self.current_meet_id = None
        else:
            label = self.meet_combo.currentText()
            self.current_meet_id = self.meets_data.get(label)
        self.load_meet_results()

    def load_meet_results(self):
        conn = self.get_db()
        cursor = conn.cursor()

        # Update team filter
        if self.current_meet_id:
            cursor.execute('SELECT DISTINCT team FROM results WHERE meet_id = ? AND team != "" ORDER BY team',
                          (self.current_meet_id,))
        else:
            cursor.execute('SELECT DISTINCT team FROM results WHERE team != "" ORDER BY team')

        self.team_combo.blockSignals(True)
        self.team_combo.clear()
        self.team_combo.addItem("All")
        for row in cursor.fetchall():
            self.team_combo.addItem(row['team'])
        self.team_combo.blockSignals(False)

        # Update event filter - strip gender prefix to avoid duplicates
        if self.current_meet_id:
            cursor.execute('SELECT DISTINCT event_name FROM results WHERE meet_id = ? ORDER BY is_relay, event_distance, event_name',
                          (self.current_meet_id,))
        else:
            cursor.execute('SELECT DISTINCT event_name FROM results ORDER BY is_relay, event_distance, event_name')

        # Strip gender prefix and relay/lead-off suffixes from event names and deduplicate
        events_set = set()
        for row in cursor.fetchall():
            event = row['event_name'] or ''
            event = self.normalize_event_for_filter(event)
            if event:
                events_set.add(event)

        self.event_combo.blockSignals(True)
        self.event_combo.clear()
        self.event_combo.addItem("All")
        # Sort events by extracting distance
        for event in sorted(events_set, key=lambda e: (self.extract_distance_for_sort(e), e)):
            self.event_combo.addItem(event)
        self.event_combo.blockSignals(False)

        # Update distance filter
        if self.current_meet_id:
            cursor.execute('SELECT DISTINCT event_distance FROM results WHERE meet_id = ? AND event_distance > 0 ORDER BY event_distance',
                          (self.current_meet_id,))
        else:
            cursor.execute('SELECT DISTINCT event_distance FROM results WHERE event_distance > 0 ORDER BY event_distance')

        self.distance_combo.blockSignals(True)
        self.distance_combo.clear()
        self.distance_combo.addItem("All")
        for row in cursor.fetchall():
            self.distance_combo.addItem(str(int(row['event_distance'])))
        self.distance_combo.blockSignals(False)

        # Update round filter
        if self.current_meet_id:
            cursor.execute('SELECT DISTINCT round FROM results WHERE meet_id = ? ORDER BY round',
                          (self.current_meet_id,))
        else:
            cursor.execute('SELECT DISTINCT round FROM results ORDER BY round')

        self.round_combo.blockSignals(True)
        self.round_combo.clear()
        self.round_combo.addItem("All")
        for row in cursor.fetchall():
            round_val = row['round']
            if round_val:
                self.round_combo.addItem(round_val)
        self.round_combo.blockSignals(False)

        conn.close()

        self.clear_filters()
        self.selected_ids.clear()
        self.update_selection_label()

    def debounced_search(self):
        self.search_timer.start(300)

    def apply_filters(self):
        conn = self.get_db()
        cursor = conn.cursor()

        conditions = []
        params = []

        if self.current_meet_id:
            conditions.append("meet_id = ?")
            params.append(self.current_meet_id)

        search = self.search_edit.text().strip()
        if search:
            conditions.append("name LIKE ?")
            params.append(f"%{search}%")

        team = self.team_combo.currentText()
        if team and team != "All":
            conditions.append("team = ?")
            params.append(team)

        event = self.event_combo.currentText()
        if event and event != "All":
            # Match events with this base name, including relay/lead-off variants and gender prefixes
            conditions.append("(event_name LIKE ? OR event_name LIKE ? OR event_name LIKE ?)")
            params.extend([f"{event}%", f"Women {event}%", f"Men {event}%"])

        stroke = self.stroke_combo.currentText()
        if stroke and stroke != "All":
            stroke_pattern = self.get_stroke_pattern(stroke)
            conditions.append("event_name LIKE ?")
            params.append(stroke_pattern)

        distance = self.distance_combo.currentText()
        if distance and distance != "All":
            conditions.append("event_distance = ?")
            params.append(int(distance))

        gender = self.gender_combo.currentText()
        if gender != "All":
            conditions.append("event_gender = ?")
            params.append(gender)

        round_filter = self.round_combo.currentText()
        if round_filter and round_filter != "All":
            conditions.append("round = ?")
            params.append(round_filter)

        if not self.show_exh_check.isChecked():
            conditions.append("is_exhibition = 0")

        if not self.show_dq_check.isChecked():
            conditions.append("is_dq = 0 AND is_scratch = 0")

        where = " AND ".join(conditions) if conditions else "1=1"

        query = f"SELECT * FROM results WHERE {where} ORDER BY is_relay, event_distance, event_name, round, place ASC"
        cursor.execute(query, params)
        rows = cursor.fetchall()
        conn.close()

        self.all_results = [dict(row) for row in rows]
        self.populate_table()

    def populate_table(self):
        self.results_table.setRowCount(0)
        self.results_table.setRowCount(len(self.all_results))

        for i, row in enumerate(self.all_results):
            rid = row['id']

            # Checkbox
            checkbox_item = QTableWidgetItem()
            checkbox_item.setCheckState(Qt.Checked if rid in self.selected_ids else Qt.Unchecked)
            checkbox_item.setData(Qt.UserRole, rid)
            self.results_table.setItem(i, 0, checkbox_item)

            # Place
            place = str(int(row['place'])) if row['place'] else "-"
            self.results_table.setItem(i, 1, QTableWidgetItem(place))

            # Name
            self.results_table.setItem(i, 2, QTableWidgetItem(row['name'] or ''))

            # Year
            self.results_table.setItem(i, 3, QTableWidgetItem(row['year'] or ''))

            # Team
            self.results_table.setItem(i, 4, QTableWidgetItem(row['team'] or ''))

            # Event
            self.results_table.setItem(i, 5, QTableWidgetItem(row['event_name'] or ''))

            # Time
            self.results_table.setItem(i, 6, QTableWidgetItem(row['finals_time'] or ''))

            # Points
            pts = f"{row['points']:.1f}" if row['points'] else ""
            self.results_table.setItem(i, 7, QTableWidgetItem(pts))

            # Round
            round_str = row.get('round') or ''
            self.results_table.setItem(i, 8, QTableWidgetItem(round_str))

            # Status
            status = ""
            color = None
            if row['is_dq']:
                status = "DQ"
                color = QColor(255, 100, 100)
            elif row['is_scratch']:
                status = "SCR"
                color = QColor(255, 100, 100)
            elif row['is_exhibition']:
                status = "EXH"
                color = QColor(180, 180, 180)
            elif row['time_standard']:
                status = row['time_standard']

            status_item = QTableWidgetItem(status)
            if color:
                status_item.setForeground(color)
            self.results_table.setItem(i, 9, status_item)

        self.status_bar.showMessage(f"Showing {len(self.all_results)} results")

    def on_results_cell_clicked(self, row, col):
        if col == 0:
            item = self.results_table.item(row, 0)
            rid = item.data(Qt.UserRole)

            if item.checkState() == Qt.Checked:
                item.setCheckState(Qt.Unchecked)
                self.selected_ids.discard(rid)
            else:
                item.setCheckState(Qt.Checked)
                self.selected_ids.add(rid)

            self.update_selection_label()

    def on_results_double_clicked(self, row, col):
        if row >= len(self.all_results):
            return

        result = self.all_results[row]

        if result['is_relay'] and result['relay_swimmers']:
            dialog = RelayDetailsDialog(self, result, DB_PATH)
            dialog.exec()
            self.update_saved_count()
        else:
            self.show_swim_details(result)

    def on_header_clicked(self, col):
        if col == 0:
            return
        self.results_table.sortItems(col, Qt.AscendingOrder if self.sort_order == Qt.DescendingOrder else Qt.DescendingOrder)
        self.sort_order = Qt.AscendingOrder if self.sort_order == Qt.DescendingOrder else Qt.DescendingOrder

    def update_selection_label(self):
        self.selection_label.setText(f"{len(self.selected_ids)} selected")

    def select_all_visible(self):
        for i in range(self.results_table.rowCount()):
            item = self.results_table.item(i, 0)
            rid = item.data(Qt.UserRole)
            item.setCheckState(Qt.Checked)
            self.selected_ids.add(rid)
        self.update_selection_label()

    def clear_selection(self):
        for i in range(self.results_table.rowCount()):
            item = self.results_table.item(i, 0)
            rid = item.data(Qt.UserRole)
            item.setCheckState(Qt.Unchecked)
            self.selected_ids.discard(rid)
        self.update_selection_label()

    def _insert_saved_result(self, cursor, row, meet_name=None, meet_date=None, meet_filename=None):
        """Insert a copy of a result into saved_results. Returns True if inserted."""
        cursor.execute('''
            INSERT OR IGNORE INTO saved_results
            (place, name, year, team, event_name, event_gender, event_distance,
             finals_time, finals_seconds, points, time_standard,
             is_relay, is_diving, is_exhibition, is_dq, is_scratch,
             round, reaction_time, dq_reason, splits, relay_swimmers,
             meet_name, meet_date, meet_filename)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        ''', (
            row['place'], row['name'], row['year'], row['team'],
            row['event_name'], row['event_gender'], row['event_distance'],
            row['finals_time'], row['finals_seconds'], row['points'],
            row['time_standard'], row['is_relay'], row['is_diving'],
            row['is_exhibition'], row['is_dq'], row['is_scratch'],
            row['round'], row['reaction_time'], row['dq_reason'],
            row['splits'], row['relay_swimmers'],
            meet_name, meet_date, meet_filename,
        ))
        return cursor.rowcount > 0

    def save_selected(self):
        if not self.selected_ids:
            QMessageBox.information(self, "Info", "No results selected.")
            return

        conn = self.get_db()
        cursor = conn.cursor()
        saved = 0
        skipped_dq = 0
        relay_legs_saved = 0

        for rid in self.selected_ids:
            # Get the result details with meet info
            cursor.execute('''
                SELECT r.*, m.meet_name, m.meet_date, m.filename AS meet_filename
                FROM results r JOIN meets m ON r.meet_id = m.id
                WHERE r.id = ?
            ''', (rid,))
            row = cursor.fetchone()
            if not row:
                continue

            # Skip DQ/SCR results
            if row['is_dq'] or row['is_scratch']:
                skipped_dq += 1
                continue

            # Save the main result as a copy
            try:
                if self._insert_saved_result(cursor, row, row['meet_name'], row['meet_date'], row['meet_filename']):
                    saved += 1

                    # If it's a relay, also save individual legs
                    if row['is_relay'] and row['relay_swimmers'] and row['splits']:
                        relay_legs_saved += self.save_relay_legs(cursor, row)
            except Exception:
                pass

        conn.commit()
        conn.close()

        already = len(self.selected_ids) - saved - skipped_dq
        self.clear_selection()

        msg = f"Saved {saved} results."
        if relay_legs_saved > 0:
            msg += f" ({relay_legs_saved} relay legs)"
        if already > 0:
            msg += f" ({already} already saved)"
        if skipped_dq > 0:
            msg += f" ({skipped_dq} DQ/SCR skipped)"

        QMessageBox.information(self, "Saved", msg)
        self.update_saved_count()

    def save_relay_legs(self, cursor, row):
        """Save individual relay legs as separate saved results (copies)."""
        relay_swimmers = json.loads(row['relay_swimmers']) if row['relay_swimmers'] else []
        splits = json.loads(row['splits']) if row['splits'] else []

        if not relay_swimmers or not splits:
            return 0

        # Calculate leg times
        leg_times = self.calculate_relay_leg_times(splits, len(relay_swimmers), row['event_distance'])

        # Determine strokes
        if 'Medley' in (row['event_name'] or ''):
            strokes = ['Backstroke', 'Breaststroke', 'Butterfly', 'Freestyle']
        else:
            strokes = ['Freestyle'] * 4

        saved_count = 0
        leg_distance = row['event_distance'] // len(relay_swimmers) if len(relay_swimmers) else 50
        meet_name = row.get('meet_name', '')
        meet_date = row.get('meet_date', '')
        meet_filename = row.get('meet_filename', '')

        for i, swimmer in enumerate(relay_swimmers):
            if i >= len(leg_times) or leg_times[i] is None:
                continue

            name, year, leg = swimmer[0], swimmer[1], swimmer[2]
            leg_time = leg_times[i]
            leg_stroke = strokes[i] if i < len(strokes) else 'Freestyle'
            leg_type = "lead-off" if leg == 1 else "relay"
            leg_event = f"{leg_distance} {leg_stroke} ({leg_type})"
            time_str = self.format_time(leg_time)

            try:
                leg_row = {
                    'place': None, 'name': name, 'year': year, 'team': row['team'],
                    'event_name': leg_event, 'event_gender': row['event_gender'],
                    'event_distance': leg_distance, 'finals_time': time_str,
                    'finals_seconds': leg_time, 'points': None, 'time_standard': None,
                    'is_relay': 0, 'is_diving': 0, 'is_exhibition': 0,
                    'is_dq': 0, 'is_scratch': 0, 'round': None,
                    'reaction_time': None, 'dq_reason': None,
                    'splits': '[]', 'relay_swimmers': '[]',
                }
                if self._insert_saved_result(cursor, leg_row, meet_name, meet_date, meet_filename):
                    saved_count += 1
            except Exception:
                pass

        return saved_count

    def calculate_relay_leg_times(self, splits, num_swimmers, event_distance):
        """Calculate individual leg times from cumulative relay splits.

        Same logic as calculate_leg_times — splits are cumulative from relay start.
        Each swimmer's leg time = their final cumulative - previous swimmer's final cumulative.
        """
        return self.calculate_leg_times(splits, num_swimmers, event_distance)

    def get_stroke_pattern(self, stroke):
        """Convert stroke name to SQL LIKE pattern for event_name matching"""
        patterns = {
            'Freestyle': '%Free%',
            'Backstroke': '%Back%',
            'Breaststroke': '%Breast%',
            'Butterfly': '%Fly%',
            'IM': '%IM%',
        }
        return patterns.get(stroke, f'%{stroke}%')

    def extract_distance_for_sort(self, event_name):
        """Extract sort key from event name: stroke first, then distance, relays last"""
        import re
        is_relay = 1 if 'Relay' in event_name else 0
        match = re.search(r'(\d+)', event_name)
        distance = int(match.group(1)) if match else 0

        name_lower = event_name.lower()
        stroke_order = {
            'free': 0, 'back': 1, 'breast': 2, 'fly': 3, 'butter': 3, 'im': 4, 'medley': 5,
        }
        stroke_idx = 99
        for key, idx in stroke_order.items():
            if key in name_lower:
                stroke_idx = idx
                break

        return (is_relay, stroke_idx, distance)

    def strip_gender_prefix(self, event_name):
        """Remove Women/Men prefix from event name"""
        if event_name.startswith('Women '):
            return event_name[6:]
        elif event_name.startswith('Men '):
            return event_name[4:]
        return event_name

    def strip_event_suffixes(self, event_name):
        """Remove (relay) and (lead-off) suffixes from event name for filtering"""
        import re
        # Remove (relay), (lead-off), or similar suffixes
        return re.sub(r'\s*\((relay|lead-off)\)\s*$', '', event_name, flags=re.IGNORECASE).strip()

    def normalize_event_for_filter(self, event_name):
        """Strip both gender prefix and relay/lead-off suffixes"""
        event = self.strip_gender_prefix(event_name)
        event = self.strip_event_suffixes(event)
        return event

    def clear_filters(self):
        self.search_edit.clear()
        self.team_combo.setCurrentIndex(0)
        self.event_combo.setCurrentIndex(0)
        self.stroke_combo.setCurrentIndex(0)
        self.distance_combo.setCurrentIndex(0)
        self.gender_combo.setCurrentIndex(0)
        self.round_combo.setCurrentIndex(0)
        self.show_exh_check.setChecked(True)
        self.show_dq_check.setChecked(True)
        self.apply_filters()

    def load_pdf(self):
        filepath, _ = QFileDialog.getOpenFileName(
            self, "Select HY-TEK Results PDF",
            str(Path.home()),
            "PDF files (*.pdf);;All files (*.*)"
        )
        if filepath:
            self.load_pdf_file(filepath)

    def load_pdf_file(self, filepath):
        try:
            self.status_bar.showMessage(f"Loading {Path(filepath).name}...")
            QApplication.processEvents()

            df, meet_info = parse_hytek_pdf(filepath, include_meet_info=True)

            if len(df) == 0:
                QMessageBox.warning(self, "Warning", "No results found in the PDF.")
                return

            meet_name = meet_info.get('meet_name') or Path(filepath).stem
            meet_date = normalize_date(meet_info.get('meet_date'))

            conn = self.get_db()
            cursor = conn.cursor()

            # Check if this meet was already loaded
            cursor.execute('SELECT id FROM meets WHERE meet_name = ? AND meet_date = ?',
                          (meet_name, meet_date))
            existing = cursor.fetchone()
            if existing:
                reply = QMessageBox.question(self, "Duplicate Meet",
                    f"'{meet_name}' is already loaded. Load again anyway?",
                    QMessageBox.Yes | QMessageBox.No)
                if reply != QMessageBox.Yes:
                    conn.close()
                    self.status_bar.showMessage("Load cancelled - meet already exists")
                    return
                meet_id = existing['id']
            else:
                cursor.execute('INSERT INTO meets (filename, meet_name, meet_date) VALUES (?, ?, ?)',
                              (Path(filepath).name, meet_name, meet_date))
                meet_id = cursor.lastrowid

            loaded_count = 0
            skipped_dup = 0
            for idx, row in df.iterrows():
                # Skip diving events
                if row.get('is_diving'):
                    continue

                try:
                    cursor.execute('''
                        INSERT OR IGNORE INTO results (meet_id, place, name, year, team, event_name, event_gender,
                            event_distance, finals_time, finals_seconds, points, time_standard,
                            is_relay, is_diving, is_exhibition, is_dq, is_scratch, round, reaction_time, dq_reason, splits, relay_swimmers)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (
                        meet_id, row.get('place'), row.get('name', ''), row.get('year', ''),
                        row.get('team', ''), row.get('event_name', ''), row.get('event_gender', ''),
                        row.get('event_distance', 0), row.get('finals_time', ''), row.get('finals_seconds'),
                        row.get('points'), row.get('time_standard', ''),
                        1 if row.get('is_relay') else 0, 0,  # is_diving always 0 now
                        1 if row.get('is_exhibition') else 0, 1 if row.get('is_dq') else 0,
                        1 if row.get('is_scratch') else 0, row.get('round'), row.get('reaction_time'),
                        row.get('dq_reason', ''),
                        json.dumps(row.get('splits', [])), json.dumps(row.get('relay_swimmers', []))
                    ))
                    if cursor.rowcount > 0:
                        loaded_count += 1
                    else:
                        skipped_dup += 1
                except sqlite3.IntegrityError:
                    skipped_dup += 1

            conn.commit()
            conn.close()

            self.current_meet_id = meet_id
            self.refresh_meets_list()

            # Select the new meet
            for i in range(self.meet_combo.count()):
                label = self.meet_combo.itemText(i)
                if label in self.meets_data and self.meets_data[label] == meet_id:
                    self.meet_combo.setCurrentIndex(i)
                    break

            self.load_meet_results()
            msg = f"Loaded {loaded_count} results from {Path(filepath).name}"
            if skipped_dup > 0:
                msg += f" ({skipped_dup} duplicates skipped)"
            self.status_bar.showMessage(msg)

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to load PDF:\n{str(e)}")
            self.status_bar.showMessage("Error loading file.")

    def delete_current_meet(self):
        if not self.current_meet_id:
            QMessageBox.warning(self, "Warning", "No meet selected.")
            return

        reply = QMessageBox.question(self, "Confirm Delete",
                                     "Delete this meet? (Saved results will be kept.)",
                                     QMessageBox.Yes | QMessageBox.No)
        if reply != QMessageBox.Yes:
            return

        conn = self.get_db()
        cursor = conn.cursor()
        # Saved results are independent copies — no cascade delete needed
        cursor.execute('DELETE FROM results WHERE meet_id = ?', (self.current_meet_id,))
        cursor.execute('DELETE FROM meets WHERE id = ?', (self.current_meet_id,))
        conn.commit()
        conn.close()

        self.current_meet_id = None
        self.refresh_meets_list()
        self.results_table.setRowCount(0)
        self.update_saved_count()
        self.status_bar.showMessage("Meet deleted")

    def on_tab_changed(self, index):
        if index == 1:
            self.load_saved_results()
        elif index == 2:
            self.load_relay_teams()
            self.compute_best_relays()

    def load_saved_results(self):
        """Load saved results and populate filter dropdowns"""
        conn = self.get_db()
        cursor = conn.cursor()

        # Populate team filter
        cursor.execute('''
            SELECT DISTINCT team FROM saved_results
            WHERE team != "" ORDER BY team
        ''')
        teams = [row['team'] for row in cursor.fetchall()]

        self.saved_team_combo.blockSignals(True)
        self.saved_team_combo.clear()
        self.saved_team_combo.addItem("All")
        for team in teams:
            self.saved_team_combo.addItem(team)
        self.saved_team_combo.blockSignals(False)

        # Populate event filter - strip gender prefix to avoid duplicates
        cursor.execute('''
            SELECT DISTINCT event_name, event_distance, is_relay FROM saved_results
            ORDER BY is_relay, event_distance, event_name
        ''')
        events_set = set()
        for row in cursor.fetchall():
            event = row['event_name'] or ''
            event = self.normalize_event_for_filter(event)
            if event:
                events_set.add(event)

        self.saved_event_combo.blockSignals(True)
        self.saved_event_combo.clear()
        self.saved_event_combo.addItem("All")
        for event in sorted(events_set, key=lambda e: (self.extract_distance_for_sort(e), e)):
            self.saved_event_combo.addItem(event)
        self.saved_event_combo.blockSignals(False)

        # Populate distance filter
        cursor.execute('''
            SELECT DISTINCT event_distance FROM saved_results
            WHERE event_distance > 0
            ORDER BY event_distance
        ''')
        distances = [row['event_distance'] for row in cursor.fetchall()]

        self.saved_distance_combo.blockSignals(True)
        self.saved_distance_combo.clear()
        self.saved_distance_combo.addItem("All")
        for dist in distances:
            self.saved_distance_combo.addItem(str(int(dist)))
        self.saved_distance_combo.blockSignals(False)

        # Populate meet filter
        cursor.execute('''
            SELECT DISTINCT meet_name, meet_filename FROM saved_results
            WHERE meet_name IS NOT NULL OR meet_filename IS NOT NULL
            ORDER BY meet_date DESC
        ''')
        meets = cursor.fetchall()

        self.saved_meet_combo.blockSignals(True)
        self.saved_meet_combo.clear()
        self.saved_meet_combo.addItem("All")
        for meet in meets:
            name = meet['meet_name'] or meet['meet_filename']
            self.saved_meet_combo.addItem(name, name)
        self.saved_meet_combo.blockSignals(False)

        conn.close()

        # Apply filters to show results
        self.apply_saved_filters()

    def debounced_saved_search(self):
        """Debounce search input for saved results"""
        self.saved_search_timer.start(300)

    def apply_saved_filters(self):
        """Apply filters to saved results"""
        conn = self.get_db()
        cursor = conn.cursor()

        conditions = []
        params = []

        search = self.saved_search_edit.text().strip()
        if search:
            conditions.append("name LIKE ?")
            params.append(f"%{search}%")

        team = self.saved_team_combo.currentText()
        if team and team != "All":
            conditions.append("team = ?")
            params.append(team)

        event = self.saved_event_combo.currentText()
        if event and event != "All":
            # Match events with this base name, including relay/lead-off variants and gender prefixes
            conditions.append("(event_name LIKE ? OR event_name LIKE ? OR event_name LIKE ?)")
            params.extend([f"{event}%", f"Women {event}%", f"Men {event}%"])

        stroke = self.saved_stroke_combo.currentText()
        if stroke and stroke != "All":
            stroke_pattern = self.get_stroke_pattern(stroke)
            conditions.append("event_name LIKE ?")
            params.append(stroke_pattern)

        distance = self.saved_distance_combo.currentText()
        if distance and distance != "All":
            conditions.append("event_distance = ?")
            params.append(int(distance))

        # Meet filter
        meet_name_filter = self.saved_meet_combo.currentData()
        if meet_name_filter:
            conditions.append("(meet_name = ? OR meet_filename = ?)")
            params.extend([meet_name_filter, meet_name_filter])

        gender = self.saved_gender_combo.currentText()
        if gender != "All":
            conditions.append("event_gender = ?")
            params.append(gender)

        where = " AND ".join(conditions) if conditions else "1=1"

        query = f'''
            SELECT * FROM saved_results
            WHERE {where}
            ORDER BY name ASC
        '''
        cursor.execute(query, params)
        rows = cursor.fetchall()
        conn.close()

        self.saved_table.setRowCount(0)
        self.saved_table.setRowCount(len(rows))

        for i, row in enumerate(rows):
            # Name column with ID stored
            name_item = QTableWidgetItem(row['name'] or '')
            name_item.setData(Qt.UserRole, row['id'])
            self.saved_table.setItem(i, 0, name_item)

            self.saved_table.setItem(i, 1, QTableWidgetItem(row['year'] or ''))
            self.saved_table.setItem(i, 2, QTableWidgetItem(row['team'] or ''))
            self.saved_table.setItem(i, 3, QTableWidgetItem(row['event_name'] or ''))
            self.saved_table.setItem(i, 4, QTableWidgetItem(row['finals_time'] or ''))
            self.saved_table.setItem(i, 5, QTableWidgetItem(row['meet_name'] or ''))
            self.saved_table.setItem(i, 6, QTableWidgetItem(row['meet_date'] or ''))

        self.saved_count_label.setText(f"{len(rows)} saved results")

    def clear_saved_filters(self):
        """Clear all saved results filters"""
        self.saved_search_edit.clear()
        self.saved_team_combo.setCurrentIndex(0)
        self.saved_event_combo.setCurrentIndex(0)
        self.saved_stroke_combo.setCurrentIndex(0)
        self.saved_distance_combo.setCurrentIndex(0)
        self.saved_meet_combo.setCurrentIndex(0)
        self.saved_gender_combo.setCurrentIndex(0)
        self.apply_saved_filters()

    def on_saved_double_clicked(self, row, col):
        """Handle double-click on saved results to show details"""
        name_item = self.saved_table.item(row, 0)  # Name is now at column 0
        if not name_item:
            return

        rid = name_item.data(Qt.UserRole)
        if not rid:
            return

        conn = self.get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM saved_results WHERE id = ?", (rid,))
        result = cursor.fetchone()
        conn.close()

        if not result:
            return

        result = dict(result)

        # Check if it's a relay with swimmer data
        if result['is_relay'] and result['relay_swimmers']:
            dialog = RelayDetailsDialog(self, result, DB_PATH, read_only=True)
            dialog.exec()
        else:
            self.show_swim_details(result)

    def show_swim_details(self, result):
        """Show details dialog for an individual swim with splits"""
        from PySide6.QtWidgets import QDialog, QVBoxLayout, QGridLayout, QFrame

        dialog = QDialog(self)
        dialog.setWindowTitle(f"Swim Details - {result['name']}")
        dialog.setMinimumSize(450, 350)

        layout = QVBoxLayout(dialog)

        # Header info
        header = QLabel(f"<b>{result['event_name']}</b>")
        header.setStyleSheet("font-size: 14px;")
        layout.addWidget(header)

        # Details grid
        grid = QGridLayout()
        grid.setSpacing(8)

        details = [
            ("Name:", result['name'] or ''),
            ("Team:", result['team'] or ''),
            ("Year:", result['year'] or ''),
            ("Time:", result['finals_time'] or ''),
        ]

        for i, (label, value) in enumerate(details):
            grid.addWidget(QLabel(f"<b>{label}</b>"), i, 0)
            grid.addWidget(QLabel(value), i, 1)

        layout.addLayout(grid)

        # Splits section with Distance | Split/50 (with /100) | Cumulative
        splits = json.loads(result['splits']) if result['splits'] else []
        if splits:
            layout.addWidget(QLabel(""))  # Spacer
            layout.addWidget(QLabel("<b>Splits:</b>"))

            splits_frame = QFrame()
            splits_frame.setFrameShape(QFrame.StyledPanel)
            splits_frame.setStyleSheet("""
                QFrame {
                    border: 1px solid palette(mid);
                    border-radius: 4px;
                    padding: 8px;
                    background-color: palette(base);
                }
            """)
            splits_layout = QGridLayout(splits_frame)
            splits_layout.setSpacing(6)

            # Header row
            splits_layout.addWidget(QLabel("<b>Distance</b>"), 0, 0)
            splits_layout.addWidget(QLabel("<b>Split/50</b>"), 0, 1)
            splits_layout.addWidget(QLabel("<b>Cumulative</b>"), 0, 2)

            split_distance = 50  # Default 50y splits
            cumulative = 0.0

            for i, split in enumerate(splits):
                row = i + 1  # Start after header
                distance = (i + 1) * split_distance
                cumulative += split

                # Distance column
                splits_layout.addWidget(QLabel(f"{distance}"), row, 0)

                # Split/50 column - show /100 pace in parentheses for even splits
                split_str = self.format_time(split)
                if (i + 1) % 2 == 0 and i > 0:
                    # Calculate per-100 for this and previous split
                    prev_split = splits[i - 1] if i > 0 else 0
                    per_100 = split + prev_split
                    split_str += f" ({self.format_time(per_100)})"
                splits_layout.addWidget(QLabel(split_str), row, 1)

                # Cumulative column
                splits_layout.addWidget(QLabel(self.format_time(cumulative)), row, 2)

            layout.addWidget(splits_frame)
        else:
            layout.addWidget(QLabel(""))
            layout.addWidget(QLabel("<i>No splits available</i>"))

        layout.addStretch()

        # Close button
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(dialog.close)
        layout.addWidget(close_btn)

        dialog.exec()

    def update_saved_count(self):
        conn = self.get_db()
        cursor = conn.cursor()
        cursor.execute('SELECT COUNT(*) as cnt FROM saved_results')
        count = cursor.fetchone()['cnt']
        conn.close()

        tab_text = f"Saved Results ({count})" if count > 0 else "Saved Results"
        self.tabs.setTabText(1, tab_text)

    def remove_saved_selected(self):
        selected_rows = set()
        for item in self.saved_table.selectedItems():
            selected_rows.add(item.row())

        if not selected_rows:
            QMessageBox.information(self, "Info", "No results selected.")
            return

        reply = QMessageBox.question(self, "Confirm",
                                     f"Remove {len(selected_rows)} results from saved?",
                                     QMessageBox.Yes | QMessageBox.No)
        if reply != QMessageBox.Yes:
            return

        conn = self.get_db()
        cursor = conn.cursor()
        for row in selected_rows:
            name_item = self.saved_table.item(row, 0)  # Name is now at column 0
            if name_item:
                rid = name_item.data(Qt.UserRole)
                cursor.execute('DELETE FROM saved_results WHERE id = ?', (rid,))
        conn.commit()
        conn.close()

        self.load_saved_results()
        self.update_saved_count()

    def export_csv(self):
        if self.results_table.rowCount() == 0:
            QMessageBox.warning(self, "Warning", "No data to export.")
            return

        filepath, _ = QFileDialog.getSaveFileName(
            self, "Export CSV",
            str(Path.home() / "Downloads" / "results.csv"),
            "CSV files (*.csv)"
        )

        if filepath:
            with open(filepath, 'w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow(['Place', 'Name', 'Year', 'Team', 'Event', 'Time', 'Points', 'Status'])
                for i in range(self.results_table.rowCount()):
                    row = []
                    for j in range(1, 9):  # Skip checkbox column
                        item = self.results_table.item(i, j)
                        row.append(item.text() if item else '')
                    writer.writerow(row)
            QMessageBox.information(self, "Success", f"Exported {self.results_table.rowCount()} results")

    def export_saved(self):
        if self.saved_table.rowCount() == 0:
            QMessageBox.warning(self, "Warning", "No saved results to export.")
            return

        filepath, _ = QFileDialog.getSaveFileName(
            self, "Export Saved Results",
            str(Path.home() / "Downloads" / "saved_results.csv"),
            "CSV files (*.csv)"
        )

        if filepath:
            with open(filepath, 'w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow(['Name', 'Year', 'Team', 'Event', 'Time', 'Meet', 'Date'])
                for i in range(self.saved_table.rowCount()):
                    row = []
                    for j in range(7):  # 7 columns: Name, Year, Team, Event, Time, Meet, Date
                        item = self.saved_table.item(i, j)
                        row.append(item.text() if item else '')
                    writer.writerow(row)
            QMessageBox.information(self, "Success", f"Exported {self.saved_table.rowCount()} saved results")


def main():
    app = QApplication(sys.argv)
    app.setStyle('Fusion')

    # Set app icon (replaces Python icon in dock)
    icon_path = Path(__file__).parent / "icon.png"
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))

    window = MeetResultsApp()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
