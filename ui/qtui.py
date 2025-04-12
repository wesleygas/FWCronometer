import sys
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QPushButton, QLabel, QComboBox, QStackedWidget,
    QHBoxLayout, QRadioButton, QButtonGroup, QSizePolicy, QFrame,
    QSpinBox, QScrollArea, QMessageBox
)
from PyQt6.QtSerialPort import QSerialPort, QSerialPortInfo
from PyQt6.QtCore import QIODevice, QTimer, Qt

import struct
from os import path
bundle_dir = path.abspath(path.dirname(__file__))


END_PACKET_DELIMITER = b'akb'
RESET_PROBE_COMMAND = b'R'
RESET_AVERAGE_PROBE = b'r'
REQUEST_AVERAGE_UPDATE = b'A'
REQUEST_PROBE_UPDATE = b'U'
CONFIGURE_AVERAGE_MODE = b'CA'
CONFIGURE_RESTORE_AVERAGE_PROBE = b'CI'
CONFIGURE_PROBE_COUNT = b'CP'

# --- Stylesheet Definition ---
path_to_qss = path.join(bundle_dir, 'stylesheet.qss')
with open(path_to_qss, "r") as f:
    STYLESHEET = f.read()

class BarrierProbe():
    def __init__(self, id):
        self.id = id
        self.pulse_time = 0

class StopwatchUI(QWidget):
    def __init__(self):
        super().__init__()
        self.max_probes = 4
        self.probe_count = 2
        self.probes = {i: BarrierProbe(i) for i in range(self.max_probes)}
        self.selected_probe_a = 0
        self.selected_probe_b = 1
        self.serial = QSerialPort()
        self.serial_buffer = b''
        
        # Set object name for the main window if needed for styling
        self.setObjectName("MainWindow")

        self.init_ui()
        self.init_serial()
        self.init_timer()
        self.apply_stylesheet() # Apply the stylesheet

    def apply_stylesheet(self):
        # Apply the stylesheet to the entire application or just this widget
        # Using app.setStyleSheet is usually better for consistency across potential dialogs
        # but self.setStyleSheet works fine if this is the only window.
        self.setStyleSheet(STYLESHEET)

    def init_ui(self):
        self.setWindowTitle("Physics Class Timer")
        self.setGeometry(200, 200, 900, 700) # Start slightly larger
        self.main_layout = QVBoxLayout(self) # Pass self to set layout on the window
        self.main_layout.setSpacing(20)
        self.main_layout.setContentsMargins(20, 20, 20, 20)

        # Top section
        top_section = QHBoxLayout()
        top_section.setSpacing(15)

        # Left side: Connection controls
        connection_group = QFrame()
        connection_group.setObjectName("GroupFrame") # For styling
        connection_layout = QVBoxLayout(connection_group)
        connection_layout.setContentsMargins(15, 15, 15, 15)

        connection_title = QLabel("Connection")
        connection_title.setObjectName("GroupTitle") # For styling
        connection_layout.addWidget(connection_title)

        port_layout = QHBoxLayout()
        port_layout.addWidget(QLabel("Port:"))

        self.port_dropdown = QComboBox()
        self.port_dropdown.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        # --- Moved connect_button creation UP ---
        self.connect_button = QPushButton("Connect")
        self.connect_button.clicked.connect(self.connect_serial)
        # --- Moved connect_button creation UP ---

        # Now call refresh_ports AFTER connect_button exists
        self.refresh_ports() # <<< Call refresh_ports here

        port_layout.addWidget(self.port_dropdown)

        self.refresh_button = QPushButton("Refresh")
        self.refresh_button.setObjectName("RefreshButton") # For specific styling
        self.refresh_button.clicked.connect(self.refresh_ports)
        port_layout.addWidget(self.refresh_button)
        connection_layout.addLayout(port_layout)

        # Add the connect button to the layout (it was already created)
        connection_layout.addWidget(self.connect_button) # <<< Add to layout here

        # Middle: Probe configuration
        probe_config_group = QFrame()
        probe_config_group.setObjectName("GroupFrame")
        probe_config_layout = QVBoxLayout(probe_config_group)
        probe_config_layout.setContentsMargins(15, 15, 15, 15)

        probe_config_title = QLabel("Probe Configuration")
        probe_config_title.setObjectName("GroupTitle")
        probe_config_layout.addWidget(probe_config_title)

        probe_count_layout = QHBoxLayout()
        probe_count_layout.addWidget(QLabel("Number of Probes:"))

        self.probe_count_spinner = QSpinBox()
        self.probe_count_spinner.setRange(1, self.max_probes)
        self.probe_count_spinner.setValue(self.probe_count)
        self.probe_count_spinner.valueChanged.connect(self.update_probe_count)
        probe_count_layout.addWidget(self.probe_count_spinner)
        probe_config_layout.addLayout(probe_count_layout)

        self.apply_config_button = QPushButton("Apply Configuration")
        self.apply_config_button.clicked.connect(self.apply_probe_configuration)
        probe_config_layout.addWidget(self.apply_config_button)

        # Right side: Mode selection
        mode_group = QFrame()
        mode_group.setObjectName("GroupFrame")
        mode_layout = QVBoxLayout(mode_group)
        mode_layout.setContentsMargins(15, 15, 15, 15)

        mode_title = QLabel("Measurement Mode")
        mode_title.setObjectName("GroupTitle")
        mode_layout.addWidget(mode_title)

        self.mode_button_group = QButtonGroup(self)

        self.instantaneous_radio = QRadioButton("Instantaneous Speed")
        self.instantaneous_radio.setChecked(True)
        self.mode_button_group.addButton(self.instantaneous_radio, 0)
        mode_layout.addWidget(self.instantaneous_radio)

        self.average_radio = QRadioButton("Average Speed")
        self.mode_button_group.addButton(self.average_radio, 1)
        mode_layout.addWidget(self.average_radio)

        self.mode_button_group.buttonClicked.connect(self.switch_mode)

        mode_layout.addStretch(1) # Add some space before the reset button

        self.reset_all_button = QPushButton("Reset All Chronometers")
        self.reset_all_button.setObjectName("ResetAllButton")
        self.reset_all_button.clicked.connect(self.reset_all_chronometers)
        mode_layout.addWidget(self.reset_all_button)

        # Add all groups to the top section
        top_section.addWidget(connection_group, 1)
        top_section.addWidget(probe_config_group, 1)
        top_section.addWidget(mode_group, 1)

        self.main_layout.addLayout(top_section)

        # Page Container
        self.pages = QStackedWidget()
        self.instantaneous_page = self.create_instantaneous_page()
        self.average_page = self.create_average_page()
        self.pages.addWidget(self.instantaneous_page)
        self.pages.addWidget(self.average_page)
        self.main_layout.addWidget(self.pages, 1)

        # Initialize UI state
        self.update_mode_availability()

    def create_instantaneous_page(self):
        page = QWidget()
        main_layout = QVBoxLayout(page)
        main_layout.setSpacing(15)
        main_layout.setContentsMargins(0, 10, 0, 10) # No horizontal margins needed

        title = QLabel("Instantaneous Speed Measurement")
        title.setObjectName("PageTitle") # Style via QSS
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(title)

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.Shape.NoFrame) # Style via QSS

        content_widget = QWidget()
        self.instantaneous_layout = QVBoxLayout(content_widget)
        self.instantaneous_layout.setSpacing(15)
        self.instantaneous_layout.setContentsMargins(10, 0, 10, 10) # Add padding around probe frames

        self.time_displays = {}
        self.reset_buttons = {}
        self.probe_frames = {}

        for probe_id in range(self.max_probes):
            frame = self.create_instantaneous_probe_frame(probe_id)
            self.probe_frames[probe_id] = frame
            self.instantaneous_layout.addWidget(frame)
            frame.setVisible(probe_id < self.probe_count)

        self.instantaneous_layout.addStretch()
        scroll_area.setWidget(content_widget)
        main_layout.addWidget(scroll_area, 1)

        explanation = QLabel("Measures the time it takes for an object to pass through a single sensor.")
        explanation.setAlignment(Qt.AlignmentFlag.AlignCenter)
        explanation.setStyleSheet("font-style: italic; color: #546e7a; padding: 10px;")
        main_layout.addWidget(explanation)

        return page

    def create_instantaneous_probe_frame(self, probe_id):
        frame = QFrame()
        frame.setObjectName("GroupFrame") # Use group styling, maybe create a specific one later
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(15, 10, 15, 10)
        layout.setSpacing(15)

        probe_label = QLabel(f"Probe {probe_id+1}:")
        probe_label.setObjectName("ProbeLabel")
        probe_label.setMinimumWidth(80) # Adjust as needed
        layout.addWidget(probe_label)

        time_display = QLabel("0.0000")
        time_display.setObjectName("TimeDisplayLabel")
        time_display.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred) # Let height adjust
        time_display.setMinimumHeight(60) # Set minimum height
        self.time_displays[probe_id] = time_display
        layout.addWidget(time_display, 3) # Give it more stretch factor

        units_label = QLabel("seconds")
        units_label.setObjectName("UnitsLabel")
        layout.addWidget(units_label)

        button = QPushButton(f"Reset")
        button.setObjectName("SmallResetButton")
        button.clicked.connect(lambda _, pid=probe_id: self.send_command(RESET_PROBE_COMMAND + bytes([pid])))
        self.reset_buttons[probe_id] = button
        layout.addWidget(button)

        return frame

    def create_average_page(self):
        page = QWidget()
        main_layout = QVBoxLayout(page)
        main_layout.setSpacing(15)
        main_layout.setContentsMargins(0, 10, 0, 10)

        title = QLabel("Average Speed Measurement")
        title.setObjectName("PageTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(title)

        self.not_enough_probes_message = QLabel(
            "Average speed measurement requires at least 2 probes.\n"
            "Please configure more probes in the Probe Configuration section."
        )
        self.not_enough_probes_message.setObjectName("NotEnoughProbesLabel")
        self.not_enough_probes_message.setVisible(False)
        main_layout.addWidget(self.not_enough_probes_message)

        self.average_scroll_area = QScrollArea()
        self.average_scroll_area.setWidgetResizable(True)
        self.average_scroll_area.setFrameShape(QFrame.Shape.NoFrame)

        content_widget = QWidget()
        self.average_layout = QVBoxLayout(content_widget)
        self.average_layout.setSpacing(15)
        self.average_layout.setContentsMargins(10, 0, 10, 10)

        self.average_chronometers = []
        self.average_layout.addStretch() # Add stretch before adding chronometers

        self.average_scroll_area.setWidget(content_widget)
        main_layout.addWidget(self.average_scroll_area, 1)

        explanation = QLabel("Measures the time it takes for an object to travel between two sensors.")
        explanation.setAlignment(Qt.AlignmentFlag.AlignCenter)
        explanation.setStyleSheet("font-style: italic; color: #546e7a; padding: 10px;")
        main_layout.addWidget(explanation)

        self.update_average_chronometers() # Call this after layout is set up
        return page

    def create_average_chronometer(self, chrono_id):
        frame = QFrame()
        frame.setObjectName("GroupFrame")
        layout = QVBoxLayout(frame)
        layout.setSpacing(10)

        title = QLabel(f"Chronometer {chrono_id+1}")
        # title.setFont(QFont("Arial", 12, QFont.Weight.Bold)) # Style via QSS? Or a new style?
        title.setStyleSheet("font-size: 12pt; font-weight: bold; color: #1565c0; margin-bottom: 5px;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        selection_layout = QHBoxLayout()
        selection_layout.setSpacing(20)

        probe_a_layout = QVBoxLayout()
        probe_a_layout.addWidget(QLabel("Start Probe:"))
        probe_a_selector = QComboBox()
        probe_a_selector.addItems([f"Probe {p+1}" for p in range(self.probe_count)])
        probe_a_selector.setCurrentIndex(0 if chrono_id == 0 else ((chrono_id * 2) % self.probe_count))
        probe_a_layout.addWidget(probe_a_selector)
        selection_layout.addLayout(probe_a_layout)

        probe_b_layout = QVBoxLayout()
        probe_b_layout.addWidget(QLabel("End Probe:"))
        probe_b_selector = QComboBox()
        probe_b_selector.addItems([f"Probe {p+1}" for p in range(self.probe_count)])
        # Ensure Probe B default is different from Probe A, handle edge case of 2 probes
        default_b_idx = 1
        if self.probe_count >= 2:
             default_b_idx = 1 if chrono_id == 0 else ((chrono_id * 2 + 1) % self.probe_count)
             # Prevent A and B being the same initially
             if default_b_idx == probe_a_selector.currentIndex():
                 default_b_idx = (default_b_idx + 1) % self.probe_count
        else: # Should not happen if checks are correct, but defensively set
            default_b_idx = 0

        probe_b_selector.setCurrentIndex(default_b_idx)
        probe_b_layout.addWidget(probe_b_selector)
        selection_layout.addLayout(probe_b_layout)

        layout.addLayout(selection_layout)

        display_layout = QHBoxLayout()
        display_layout.setSpacing(15)

        time_display = QLabel("0.0000")
        time_display.setObjectName("TimeDisplayLabel")
        time_display.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        time_display.setMinimumHeight(60)
        display_layout.addWidget(time_display, 3) # Give more stretch

        units_label = QLabel("seconds")
        units_label.setObjectName("UnitsLabel")
        display_layout.addWidget(units_label)

        layout.addLayout(display_layout)

        # Add reset button to the same horizontal layout as time/units?
        reset_button = QPushButton("Reset")
        reset_button.setObjectName("SmallResetButton")
        display_layout.addWidget(reset_button)

        # Connect signals
        def update_probes():
            probe_a_idx = probe_a_selector.currentIndex()
            probe_b_idx = probe_b_selector.currentIndex()
            self.configure_specific_average_mode(chrono_id, probe_a_idx, probe_b_idx)

        probe_a_selector.currentIndexChanged.connect(update_probes)
        probe_b_selector.currentIndexChanged.connect(update_probes)

        reset_button.clicked.connect(lambda: self.reset_specific_average(
            chrono_id,
            # probe_a_selector.currentIndex(),
            # probe_b_selector.currentIndex()
        ))

        chronometer = {
            'frame': frame,
            'probe_a_selector': probe_a_selector,
            'probe_b_selector': probe_b_selector,
            'time_display': time_display,
            'reset_button': reset_button
        }

        if self.probe_count >= 2:
            update_probes() # Send initial config

        return chronometer

    def update_average_chronometers(self):
        if self.probe_count < 2:
            self.not_enough_probes_message.setVisible(True)
            self.average_scroll_area.setVisible(False)
            for chrono in self.average_chronometers:
                chrono['frame'].setParent(None)
                chrono['frame'].deleteLater() # Clean up memory
            self.average_chronometers.clear()
            return

        self.not_enough_probes_message.setVisible(False)
        self.average_scroll_area.setVisible(True)

        # Remove old chronometers first
        for chrono in self.average_chronometers:
            chrono['frame'].setParent(None)
            chrono['frame'].deleteLater()
        self.average_chronometers.clear()

        max_chronos = max(1, self.probe_count // 2)

        # Insert chronometers before the stretch item
        stretch_index = self.average_layout.count() - 1 # Index of the stretch item
        for i in range(max_chronos):
            chrono = self.create_average_chronometer(i)
            self.average_layout.insertWidget(stretch_index + i, chrono['frame']) # Insert before stretch
            self.average_chronometers.append(chrono)

    def configure_specific_average_mode(self, chrono_id, probe_a_idx, probe_b_idx):
        # Add check to prevent sending if A == B
        if probe_a_idx == probe_b_idx:
            print("UI:", f"Warning: Attempted to configure average mode {chrono_id} with same start/end probe {probe_a_idx}. Command not sent.")
            # Optionally reset the time display here
            if chrono_id < len(self.average_chronometers):
                self.average_chronometers[chrono_id]['time_display'].setText("ERR") # Indicate error state
            return

        if 0 <= probe_a_idx < 256 and 0 <= probe_b_idx < 256 and 0 <= chrono_id < 256:
            self.send_command(CONFIGURE_AVERAGE_MODE + bytes([chrono_id, probe_a_idx, probe_b_idx]))

    def restore_specific_average(self, chrono_id):
        # Restore DP objects and probe configurations
        self.send_command(CONFIGURE_RESTORE_AVERAGE_PROBE + bytes([chrono_id]))

    def reset_specific_average(self, chrono_id):
        self.send_command(RESET_AVERAGE_PROBE + bytes([chrono_id]))
        self.average_chronometers[chrono_id]['time_display'].setText("0.0000")


    def update_mode_availability(self):
        if self.probe_count < 2:
            if self.pages.currentIndex() == 1:
                self.instantaneous_radio.setChecked(True)
                self.pages.setCurrentIndex(0)
            self.average_radio.setEnabled(False)
            self.average_radio.setToolTip("Average mode requires at least 2 probes")
        else:
            self.average_radio.setEnabled(True)
            self.average_radio.setToolTip("")

    def switch_mode(self, button):
        index = self.mode_button_group.id(button)

        if index == 1 and self.probe_count < 2:
             # This check should ideally prevent the click if disabled, but double-check
            QMessageBox.warning(
                self, "Not Enough Probes",
                "Average speed measurement requires at least 2 probes.\n"
                "Please configure more probes in the Probe Configuration section."
            )
            self.instantaneous_radio.setChecked(True) # Revert selection
            return

        self.pages.setCurrentIndex(index)

        
        if index == 0: # Instantaneous mode
            # Restore any possible average mode
            for chron in range(len(self.average_chronometers)):
                self.restore_specific_average(chron)
        elif index == 1: # Re-configure average modes when switching *to* average mode
            for i, chrono in enumerate(self.average_chronometers):
                probe_a_idx = chrono['probe_a_selector'].currentIndex()
                probe_b_idx = chrono['probe_b_selector'].currentIndex()
                self.configure_specific_average_mode(i, probe_a_idx, probe_b_idx)

    def update_probe_count(self, count):
        old_count = self.probe_count
        self.probe_count = count

        # Update visibility of probe frames in instantaneous mode
        for probe_id, frame in self.probe_frames.items():
            frame.setVisible(probe_id < count)

        # Update mode availability (might disable average mode)
        self.update_mode_availability()
        old_max_chronos = max(0, old_count // 2)
        new_max_chronos = max(0, self.probe_count // 2)

        if new_max_chronos != old_max_chronos or (old_count < 2 and self.probe_count >= 2):
             self.update_average_chronometers()
        else:
             # Only update the dropdowns in existing average chronos if needed
             self.update_average_selectors()


    def update_average_selectors(self):
        """Updates the items in the average mode probe selectors."""
        for chrono in self.average_chronometers:
            current_a = chrono['probe_a_selector'].currentIndex()
            current_b = chrono['probe_b_selector'].currentIndex()

            # Block signals while updating items to prevent accidental configuration commands
            chrono['probe_a_selector'].blockSignals(True)
            chrono['probe_b_selector'].blockSignals(True)

            chrono['probe_a_selector'].clear()
            chrono['probe_b_selector'].clear()

            items = [f"Probe {p+1}" for p in range(self.probe_count)]
            chrono['probe_a_selector'].addItems(items)
            chrono['probe_b_selector'].addItems(items)

            # Restore selections if possible
            if current_a < self.probe_count:
                chrono['probe_a_selector'].setCurrentIndex(current_a)
            else:
                # Default if previous index out of bounds
                chrono['probe_a_selector'].setCurrentIndex(0)

            if current_b < self.probe_count:
                chrono['probe_b_selector'].setCurrentIndex(current_b)
            else:
                 # Default if previous index out of bounds, try to avoid selecting same as A
                new_b_idx = 1 if self.probe_count > 1 else 0
                if new_b_idx == chrono['probe_a_selector'].currentIndex():
                    new_b_idx = (new_b_idx + 1) % self.probe_count
                chrono['probe_b_selector'].setCurrentIndex(new_b_idx)


            # Unblock signals
            chrono['probe_a_selector'].blockSignals(False)
            chrono['probe_b_selector'].blockSignals(False)


    def apply_probe_configuration(self):
        # Update selectors *before* sending command, so they are correct when command is processed
        self.update_average_selectors()

        # Re-configure average modes based on current selections *after* updating selectors
        if self.pages.currentIndex() == 1: # If in average mode
            for i, chrono in enumerate(self.average_chronometers):
                probe_a_idx = chrono['probe_a_selector'].currentIndex()
                probe_b_idx = chrono['probe_b_selector'].currentIndex()
                self.configure_specific_average_mode(i, probe_a_idx, probe_b_idx)

        # Send configuration command to the microcontroller
        self.send_command(CONFIGURE_PROBE_COUNT + bytes([self.probe_count]))

        QMessageBox.information(self, "Configuration Applied",
                                f"Number of active probes set to {self.probe_count}.")


    def reset_all_chronometers(self):
        print("UI:", "Resetting all active probes")
        # Reset all *active* probes
        if self.pages.currentIndex() == 0:
            for probe_id in range(self.probe_count):
                self.send_command(RESET_PROBE_COMMAND + bytes([probe_id]))

            # Also clear UI displays immediately
            for probe_id in range(self.probe_count):
                if probe_id in self.time_displays:
                    self.time_displays[probe_id].setText("0.0000")
        elif self.pages.currentIndex() == 1:
            for i, chrono in enumerate(self.average_chronometers):
                self.reset_specific_average(i)
                chrono['time_display'].setText("0.0000")


    def init_serial(self):
        self.serial.setBaudRate(115200)
        self.serial.readyRead.connect(self.read_serial_data)
        self.serial.errorOccurred.connect(self.handle_serial_error) # Add error handling

    def connect_serial(self):
        if self.serial.isOpen():
            self.serial.close()
            print("UI:", "Disconnected.")
            self.connect_button.setText("Connect")
            self.connect_button.setStyleSheet("") # Reset style
            # Optionally reset port dropdown state or show disconnected status
            return

        selected_port = self.port_dropdown.currentText().split(" | ")[0].strip() # Get the port name from the dropdown
        if not selected_port:
             QMessageBox.warning(self, "Connection Error", "No serial port selected.")
             return

        print("UI:", "selected port", selected_port)
        self.serial.setPortName(selected_port)
        if self.serial.open(QIODevice.OpenModeFlag.ReadWrite):
            print("UI:", f"Successfully connected to {selected_port}")
            self.connect_button.setText("Disconnect")
            # Change button style on connect for visual feedback
            self.connect_button.setStyleSheet("background-color: #4caf50;") # Green when connected

            # Send the initial probe count configuration upon connection
            self.apply_probe_configuration()
            # Start polling timer only after connection? Or let it run always?
            # Let's ensure timer is running.
            if not self.timer.isActive():
                self.timer.start(200) # Poll every 200ms

        else:
            QMessageBox.critical(self, "Connection Failed",
                                f"Failed to open serial port {selected_port}.\n"
                                f"Error: {self.serial.errorString()}")
            self.connect_button.setText("Connect")
            self.connect_button.setStyleSheet("") # Reset style

    def handle_serial_error(self, error):
        # Ignore certain errors like "Resource temporarily unavailable" which can happen during close
        if error == QSerialPort.SerialPortError.ResourceError:
            print("UI:", "Serial resource error occurred (possibly during disconnect).")
            # If port is open and we get this, it might be a real issue
            if self.serial.isOpen():
                 self.serial.close()
                 self.connect_button.setText("Connect")
                 self.connect_button.setStyleSheet("")
                 QMessageBox.warning(self, "Serial Port Error", f"Serial port resource error: {self.serial.errorString()}. Disconnecting.")
            else:
                print("UI:", "Serial port is closed, probably the device has been disconnected.")
                ## Disconnecting
                self.connect_serial()


        elif error != QSerialPort.SerialPortError.NoError:
             # Handle other errors more explicitly
            error_message = f"Serial port error: {self.serial.errorString()} (Code: {error})"
            print("UI:", error_message)
            if self.serial.isOpen():
                QMessageBox.warning(self, "Serial Port Error", f"{error_message}. Check connection.")
                # Consider disconnecting automatically on severe errors
                # self.serial.close()
                # self.connect_button.setText("Connect")
                # self.connect_button.setStyleSheet("")


    def refresh_ports(self):
        current_port = self.port_dropdown.currentText()
        self.port_dropdown.clear()
        ports = QSerialPortInfo.availablePorts()
        if not ports:
            self.port_dropdown.addItem("No ports found")
            self.port_dropdown.setEnabled(False)
            self.connect_button.setEnabled(False)
        else:
            for port in ports:
                # Add more info like description if available
                description = f" ({port.description()})" if port.description() else ""
                manufacturer = f" [{port.manufacturer()}]" if port.manufacturer() else ""
                self.port_dropdown.addItem(f"{port.portName()} | {description}{manufacturer}", port.portName()) # Store portName as UserData
            self.port_dropdown.setEnabled(True)
            self.connect_button.setEnabled(True)

            # Find index by stored portName (UserData)
            index_to_restore = -1
            for i in range(self.port_dropdown.count()):
                if self.port_dropdown.itemData(i) == current_port:
                    index_to_restore = i
                    break
            if index_to_restore >= 0:
                self.port_dropdown.setCurrentIndex(index_to_restore)
            elif self.port_dropdown.count() > 0:
                 self.port_dropdown.setCurrentIndex(0) # Default to first port if previous one gone


    def send_command(self, command: bytes):
        if self.serial.isOpen() and self.serial.isWritable():
            #print("UI:", f"Sending: {command + END_PACKET_DELIMITER}") # Debug
            self.serial.write(command + END_PACKET_DELIMITER)
        elif not self.serial.isOpen():
            print("UI:", "Serial port not open. Cannot send command.")
        else: # Port is open but not writable?
            print("UI:", "Serial port not writable. Cannot send command.")


    def read_serial_data(self):
        if not self.serial.bytesAvailable():
            return
        self.serial_buffer += self.serial.readAll().data()

        # Process all complete packets in the buffer
        while END_PACKET_DELIMITER in self.serial_buffer:
            #print("UI:", self.serial_buffer) # Debug
            pkt, self.serial_buffer = self.serial_buffer.split(END_PACKET_DELIMITER, 1)

            # Add basic validation for packet length
            if not pkt: # Skip empty packets
                continue

            command_code = bytes([pkt[0]]) # Get the first byte as command code
            payload = pkt[1:]

            try:
                if command_code == REQUEST_AVERAGE_UPDATE and len(payload) >= 5: # 1 byte chrono_id + 4 bytes time
                    chrono_id, average_time = struct.unpack('<BL', payload[:5])
                    # print("UI:", f"Parsed Average Update: Chrono ID {chrono_id}, Time {average_time}") # Debug
                    self.update_specific_average_display(chrono_id, average_time)
                elif command_code == REQUEST_PROBE_UPDATE and len(payload) >= 5: # 1 byte probe_id + 4 bytes time
                    probe_id, pulse_time = struct.unpack('<BL', payload[:5])
                    # print("UI:", f"Parsed Probe Update: Probe ID {probe_id}, Time {pulse_time}") # Debug
                    self.update_instantaneous_display(probe_id, pulse_time)
                elif command_code == b'OK':
                    pass
                else:
                    print("UI:", f"Warning: Received unknown or malformed packet: {pkt}")
            except struct.error as e:
                print("UI:", f"Error unpacking packet {pkt}: {e}")
            except IndexError as e:
                print("UI:", f"Error processing packet {pkt} due to insufficient length: {e}")


    def update_specific_average_display(self, chrono_id, average_time):
        if chrono_id < len(self.average_chronometers):
            # Convert microseconds to seconds for display
            time_sec = average_time * 1e-6
            self.average_chronometers[chrono_id]['time_display'].setText(f"{time_sec:.4f}")
        else:
            print("UI:", f"Warning: Received average update for invalid chronometer ID: {chrono_id}")


    def update_instantaneous_display(self, probe_id, pulse_time):
        if probe_id in self.time_displays:
             # Convert microseconds to seconds for display
            time_sec = pulse_time * 1e-6
            self.time_displays[probe_id].setText(f"{time_sec:.4f}")
        else:
             # Don't warn if probe_id >= self.probe_count, as we might receive data for inactive probes
             if probe_id < self.max_probes:
                 pass # Silently ignore updates for probes not currently displayed/configured
             else:
                 print("UI:", f"Warning: Received instantaneous update for invalid probe ID: {probe_id}")


    def init_timer(self):
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.poll_current_mode)
        # Don't start the timer immediately, start it upon successful connection
        # self.timer.start(200)


    def poll_current_mode(self):
        if not self.serial.isOpen():
            return

        current_page_index = self.pages.currentIndex()

        if current_page_index == 0:  # Instantaneous mode
            # Only poll *active* probes
            for probe_id in range(self.probe_count):
                self.send_command(REQUEST_PROBE_UPDATE + bytes([probe_id]))
        elif current_page_index == 1:  # Average mode
            # Poll each *configured* average chronometer
            for i in range(len(self.average_chronometers)):
                self.send_command(REQUEST_AVERAGE_UPDATE + bytes([i]))


    def resizeEvent(self, event):
        super().resizeEvent(event)
        # Adjust font sizes dynamically based on window width if desired
        # This complements the base sizes set in QSS
        width = self.width()

        # Example scaling - adjust thresholds and sizes as needed
        if width > 1100:
            display_font_size = 44
        elif width > 850:
            display_font_size = 38
        elif width > 650:
            display_font_size = 30
        else:
            display_font_size = 24

        # Update font sizes for time displays using dynamic property or iterate
        for display in self.findChildren(QLabel, "TimeDisplayLabel"):
            font = display.font() # Get current font
            font.setPointSize(display_font_size)
            display.setFont(font)


    def closeEvent(self, event):
        # Ensure serial port is closed when the window closes
        if self.serial.isOpen():
            print("UI:", "Closing serial port...")
            self.serial.close()
        event.accept()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = StopwatchUI()
    window.show()
    sys.exit(app.exec())