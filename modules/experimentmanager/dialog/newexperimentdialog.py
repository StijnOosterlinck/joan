from .newexperimentdialog_ui import Ui_Dialog
from PyQt5 import QtWidgets, QtGui, QtCore


class NewExperimentDialog(QtWidgets.QDialog):
    def __init__(self, all_modules_in_settings, parent=None):
        super().__init__(parent)
        self.checkboxes = {}
        self.ui = Ui_Dialog()
        self.ui.setupUi(self)

        self._fill_module_box(all_modules_in_settings)
        self.ui.browsePushButton.clicked.connect(self._browse_file)

        self.file_path = ""
        self.modules_to_include = []

        self.show()

    def _fill_module_box(self, all_modules_in_settings):
        for module in all_modules_in_settings:
            checkbox = QtWidgets.QCheckBox(str(module))
            self.checkboxes[module] = checkbox
            self.ui.modulesGroupBox.layout().addWidget(checkbox)

    def _browse_file(self):
        path_to_file, _ = QtWidgets.QFileDialog.getSaveFileName(self, "Save experiment to...", filter='JSON (*.json)')
        if path_to_file:
            self.ui.fileLineEdit.setText(path_to_file)

    def accept(self):
        self.file_path = self.ui.fileLineEdit.text()

        self.modules_to_include = []
        for module, checkbox in self.checkboxes.items():
            if checkbox.isChecked():
                self.modules_to_include.append(module)
        super().accept()
