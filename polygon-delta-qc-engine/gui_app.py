"""
Polygon Delta QC Engine — Desktop GUI
---------------------------------------
PyQt5 desktop app wrapping `compare_polygon_datasets` (see
polygon_delta_qc_engine.py) in a background thread, with folder
browsers, a live process log, and a progress bar — for interactive use
without touching a script.

All comparison logic lives in polygon_delta_qc_engine.py and is fully
testable headlessly (see example_usage.py); this file is purely the UI
layer on top of it.

Run: python gui_app.py
Requirements: PyQt5, plus everything polygon_delta_qc_engine.py needs.
"""

import sys
import os

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QFileDialog, QTextEdit, QMessageBox, QProgressBar,
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal

from polygon_delta_qc_engine import compare_polygon_datasets, DEFAULT_ID_COLUMN, DEFAULT_AREA_COLUMN


class ComparisonThread(QThread):
    progress_signal = pyqtSignal(str)
    feeder_progress = pyqtSignal(int, int)
    finished_signal = pyqtSignal(bool, str)

    def __init__(self, reference_folder, comparison_folder, output_path, id_column, area_column):
        super().__init__()
        self.reference_folder = reference_folder
        self.comparison_folder = comparison_folder
        self.output_path = output_path
        self.id_column = id_column
        self.area_column = area_column

    def run(self):
        try:
            result = compare_polygon_datasets(
                self.reference_folder, self.comparison_folder, self.output_path,
                id_column=self.id_column, area_column=self.area_column,
                log=self.progress_signal.emit,
                progress_callback=self.feeder_progress.emit,
            )
            if result:
                self.finished_signal.emit(True, f"Report saved to:\n{result}")
            else:
                self.finished_signal.emit(False, "No feeders were processed — check the log above.")
        except Exception as e:
            import traceback
            self.finished_signal.emit(False, f"Error: {e}\n\n{traceback.format_exc()}")


class PolygonDeltaQCEngine(QMainWindow):
    def __init__(self):
        super().__init__()
        self.thread = None
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle("Polygon Delta QC Engine")
        self.setGeometry(100, 100, 950, 700)

        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout()
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(10)
        central.setLayout(layout)

        title = QLabel("Polygon Delta QC Engine")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("font-size: 20pt; font-weight: bold; color: #2c3e50; padding: 8px;")
        layout.addWidget(title)

        subtitle = QLabel("Reference vs Comparison polygon-dataset delta analyzer")
        subtitle.setAlignment(Qt.AlignCenter)
        subtitle.setStyleSheet("color: #7f8c8d; padding-bottom: 8px;")
        layout.addWidget(subtitle)

        form = QWidget()
        form_layout = QVBoxLayout()
        form.setLayout(form_layout)
        form.setStyleSheet("QWidget { background-color: #ecf0f1; border-radius: 5px; padding: 15px; }")

        self.ref_path = self._add_folder_row(form_layout, "Reference Folder:", "ref")
        self.comp_path = self._add_folder_row(form_layout, "Comparison Folder:", "comp")
        self.out_path = self._add_folder_row(form_layout, "Excel Output Folder:", "out")

        id_row = QHBoxLayout()
        id_row.addWidget(QLabel("ID Column:"))
        self.id_field = QLineEdit(DEFAULT_ID_COLUMN)
        id_row.addWidget(self.id_field)
        id_row.addWidget(QLabel("Area Column:"))
        self.area_field = QLineEdit(DEFAULT_AREA_COLUMN)
        id_row.addWidget(self.area_field)
        form_layout.addLayout(id_row)

        layout.addWidget(form)

        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        layout.addWidget(QLabel("Process Log:"))
        self.log_area = QTextEdit()
        self.log_area.setReadOnly(True)
        self.log_area.setStyleSheet(
            "QTextEdit { background-color: #2c3e50; color: #ecf0f1; font-family: monospace; }"
        )
        layout.addWidget(self.log_area)

        self.run_button = QPushButton("Run Comparison")
        self.run_button.setMinimumHeight(40)
        self.run_button.clicked.connect(self.run_comparison)
        layout.addWidget(self.run_button)

    def _add_folder_row(self, parent_layout, label_text, key):
        row = QHBoxLayout()
        label = QLabel(label_text)
        label.setMinimumWidth(150)
        field = QLineEdit()
        browse = QPushButton("Browse")
        browse.clicked.connect(lambda: self._browse(field))
        row.addWidget(label)
        row.addWidget(field)
        row.addWidget(browse)
        parent_layout.addLayout(row)
        return field

    def _browse(self, field):
        folder = QFileDialog.getExistingDirectory(self, "Select Folder")
        if folder:
            field.setText(folder)

    def log(self, message):
        self.log_area.append(message)

    def update_progress(self, current, total):
        if total > 0:
            pct = int((current / total) * 100)
            self.progress_bar.setValue(pct)
            self.progress_bar.setFormat(f"{current}/{total} feeders ({pct}%)")

    def run_comparison(self):
        ref, comp, out = self.ref_path.text().strip(), self.comp_path.text().strip(), self.out_path.text().strip()
        if not (ref and comp and out):
            QMessageBox.warning(self, "Missing Input", "Please select all three folders.")
            return
        if not all(os.path.isdir(p) for p in (ref, comp, out)):
            QMessageBox.warning(self, "Invalid Path", "One or more selected folders don't exist.")
            return

        output_file = os.path.join(out, "Polygon_Delta_QC_Report.xlsx")
        self.log_area.clear()
        self.run_button.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)

        self.thread = ComparisonThread(
            ref, comp, output_file, self.id_field.text().strip(), self.area_field.text().strip(),
        )
        self.thread.progress_signal.connect(self.log)
        self.thread.feeder_progress.connect(self.update_progress)
        self.thread.finished_signal.connect(self.on_finished)
        self.thread.start()

    def on_finished(self, success, message):
        self.run_button.setEnabled(True)
        self.progress_bar.setVisible(False)
        if success:
            QMessageBox.information(self, "Done", message)
        else:
            QMessageBox.critical(self, "Error", message)


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    window = PolygonDeltaQCEngine()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
