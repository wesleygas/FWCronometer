import sys
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QPushButton, QLabel, QComboBox, QStackedWidget, 
    QHBoxLayout, QRadioButton, QButtonGroup, QSizePolicy, QFrame,
    QSpinBox, QScrollArea, QMessageBox
)
from PyQt6.QtSerialPort import QSerialPort, QSerialPortInfo
from PyQt6.QtCore import QIODevice, QTimer, Qt
from PyQt6.QtGui import QFont

import struct

END_PACKET_DELIMITER = b'akb'
RESET_PROBE_COMMAND = b'R'
REQUEST_PROBE_UPDATE = b'U'
CONFIGURE_AVERAGE_MODE = b'CA'
REQUEST_AVERAGE_UPDATE = b'A'
CONFIGURE_PROBE_COUNT = b'CP'

class BarrierProbe():
    def __init__(self, id):
        self.id = id
        self.pulse_time = 0

class StopwatchUI(QWidget):
    def __init__(self):
        super().__init__()
        self.max_probes = 4  # Maximum number of probes supported
        self.probe_count = 2  # Default probe count
        self.probes = {i: BarrierProbe(i) for i in range(self.max_probes)}
        self.selected_probe_a = 0
        self.selected_probe_b = 1
        self.serial = QSerialPort()
        self.init_ui()
        self.init_serial()
        self.init_timer()
        self.serial_buffer = b''
        
    def init_ui(self):
        self.setWindowTitle("Physics Class Timer")
        self.setGeometry(200, 200, 900, 700)
        self.main_layout = QVBoxLayout()
        self.main_layout.setSpacing(20)
        self.main_layout.setContentsMargins(20, 20, 20, 20)
        
        # Top section with connection controls, mode selection, and probe configuration
        top_section = QHBoxLayout()
        
        # Left side: Connection controls
        connection_group = QFrame()
        connection_group.setFrameShape(QFrame.Shape.StyledPanel)
        connection_layout = QVBoxLayout(connection_group)
        connection_layout.setContentsMargins(10, 10, 10, 10)
        
        connection_title = QLabel("Connection")
        connection_title.setFont(QFont("Arial", 12, QFont.Weight.Bold))
        connection_layout.addWidget(connection_title)
        
        port_layout = QHBoxLayout()
        port_layout.addWidget(QLabel("Port:"))
        
        self.port_dropdown = QComboBox()
        self.port_dropdown.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.refresh_ports()
        port_layout.addWidget(self.port_dropdown)
        
        self.refresh_button = QPushButton("Refresh")
        self.refresh_button.clicked.connect(self.refresh_ports)
        port_layout.addWidget(self.refresh_button)
        connection_layout.addLayout(port_layout)
        
        self.connect_button = QPushButton("Connect")
        self.connect_button.clicked.connect(self.connect_serial)
        connection_layout.addWidget(self.connect_button)
        
        # Middle: Probe configuration
        probe_config_group = QFrame()
        probe_config_group.setFrameShape(QFrame.Shape.StyledPanel)
        probe_config_layout = QVBoxLayout(probe_config_group)
        probe_config_layout.setContentsMargins(10, 10, 10, 10)
        
        probe_config_title = QLabel("Probe Configuration")
        probe_config_title.setFont(QFont("Arial", 12, QFont.Weight.Bold))
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
        mode_group.setFrameShape(QFrame.Shape.StyledPanel)
        mode_layout = QVBoxLayout(mode_group)
        mode_layout.setContentsMargins(10, 10, 10, 10)
        
        mode_title = QLabel("Measurement Mode")
        mode_title.setFont(QFont("Arial", 12, QFont.Weight.Bold))
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
        
        # Add the reset all button
        self.reset_all_button = QPushButton("Reset All Chronometers")
        self.reset_all_button.setFont(QFont("Arial", 10, QFont.Weight.Bold))
        self.reset_all_button.clicked.connect(self.reset_all_chronometers)
        mode_layout.addWidget(self.reset_all_button)
        
        # Add all groups to the top section
        top_section.addWidget(connection_group, 1)
        top_section.addWidget(probe_config_group, 1)
        top_section.addWidget(mode_group, 1)
        
        # Add top section to main layout
        self.main_layout.addLayout(top_section)
        
        # Page Container
        self.pages = QStackedWidget()
        self.instantaneous_page = self.create_instantaneous_page()
        self.average_page = self.create_average_page()
        self.pages.addWidget(self.instantaneous_page)
        self.pages.addWidget(self.average_page)
        self.main_layout.addWidget(self.pages, 1)  # Give it a stretch factor for resizing
        
        self.setLayout(self.main_layout)
        
        # Initialize UI state
        self.update_mode_availability()
    
    def create_instantaneous_page(self):
        page = QWidget()
        main_layout = QVBoxLayout()
        main_layout.setSpacing(20)
        
        # Title
        title = QLabel("Instantaneous Speed Measurement")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setFont(QFont("Arial", 14, QFont.Weight.Bold))
        main_layout.addWidget(title)
        
        # Scroll area for multiple chronometers
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        
        content_widget = QWidget()
        self.instantaneous_layout = QVBoxLayout(content_widget)
        self.instantaneous_layout.setSpacing(15)
        
        # Time displays with labels
        self.time_displays = {}
        self.reset_buttons = {}
        self.probe_frames = {}
        
        for probe_id in range(self.max_probes):
            frame = self.create_instantaneous_probe_frame(probe_id)
            self.probe_frames[probe_id] = frame
            self.instantaneous_layout.addWidget(frame)
            # Initially only show configured number of probes
            frame.setVisible(probe_id < self.probe_count)
            
        self.instantaneous_layout.addStretch()
        
        scroll_area.setWidget(content_widget)
        main_layout.addWidget(scroll_area, 1)
        
        # Add explanation at the bottom
        explanation = QLabel("Measures the time it takes for an object to pass through a single sensor.")
        explanation.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(explanation)
        
        page.setLayout(main_layout)
        return page
    
    def create_instantaneous_probe_frame(self, probe_id):
        frame = QFrame()
        frame.setFrameShape(QFrame.Shape.StyledPanel)
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(10, 10, 10, 10)
        
        # Label for the probe
        probe_label = QLabel(f"Probe {probe_id+1}:")
        probe_label.setFont(QFont("Arial", 12, QFont.Weight.Bold))
        probe_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        probe_label.setMinimumWidth(100)
        layout.addWidget(probe_label)
        
        # Time display
        time_display = QLabel("0.0000")
        time_display.setFont(QFont("Courier", 36, QFont.Weight.Bold))
        time_display.setAlignment(Qt.AlignmentFlag.AlignCenter)
        time_display.setFrameShape(QFrame.Shape.StyledPanel)
        time_display.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        time_display.setMinimumHeight(80)
        self.time_displays[probe_id] = time_display
        layout.addWidget(time_display, 3)
        
        # Units label
        units_label = QLabel("seconds")
        units_label.setFont(QFont("Arial", 12))
        units_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(units_label)
        
        # Reset button
        button = QPushButton(f"Reset")
        button.setFont(QFont("Arial", 10))
        button.clicked.connect(lambda _, pid=probe_id: self.send_command(RESET_PROBE_COMMAND + bytes([pid])))
        self.reset_buttons[probe_id] = button
        layout.addWidget(button)
        
        return frame
    
    def create_average_page(self):
        page = QWidget()
        main_layout = QVBoxLayout()
        main_layout.setSpacing(20)
        
        # Title
        title = QLabel("Average Speed Measurement")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setFont(QFont("Arial", 14, QFont.Weight.Bold))
        main_layout.addWidget(title)
        
        # Message for when there are not enough probes
        self.not_enough_probes_message = QLabel(
            "Average speed measurement requires at least 2 probes.\n"
            "Please configure more probes in the Probe Configuration section."
        )
        self.not_enough_probes_message.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.not_enough_probes_message.setFont(QFont("Arial", 12))
        self.not_enough_probes_message.setStyleSheet("color: red;")
        self.not_enough_probes_message.setVisible(False)
        main_layout.addWidget(self.not_enough_probes_message)
        
        # Scroll area for multiple chronometers
        self.average_scroll_area = QScrollArea()
        self.average_scroll_area.setWidgetResizable(True)
        self.average_scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        
        content_widget = QWidget()
        self.average_layout = QVBoxLayout(content_widget)
        self.average_layout.setSpacing(15)
        
        # We'll dynamically create average chronometers based on the number of probes
        self.average_chronometers = []
        
        # Add a stretch to push chronometers to the top
        self.average_layout.addStretch()
        
        self.average_scroll_area.setWidget(content_widget)
        main_layout.addWidget(self.average_scroll_area, 1)
        
        # Add explanation at the bottom
        explanation = QLabel("Measures the time it takes for an object to travel between two sensors.")
        explanation.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(explanation)
        
        page.setLayout(main_layout)
        self.update_average_chronometers()
        return page
    
    def create_average_chronometer(self, chrono_id):
        frame = QFrame()
        frame.setFrameShape(QFrame.Shape.StyledPanel)
        layout = QVBoxLayout(frame)
        
        # Chronometer title
        title = QLabel(f"Chronometer {chrono_id+1}")
        title.setFont(QFont("Arial", 12, QFont.Weight.Bold))
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)
        
        # Probe selection
        selection_layout = QHBoxLayout()
        
        # Probe A selection
        probe_a_layout = QVBoxLayout()
        probe_a_layout.addWidget(QLabel("Start Probe:"))
        probe_a_selector = QComboBox()
        probe_a_selector.addItems([f"Probe {p+1}" for p in range(self.probe_count)])
        probe_a_selector.setCurrentIndex(0 if chrono_id == 0 else ((chrono_id * 2) % self.probe_count))
        probe_a_layout.addWidget(probe_a_selector)
        selection_layout.addLayout(probe_a_layout)
        
        # Probe B selection
        probe_b_layout = QVBoxLayout()
        probe_b_layout.addWidget(QLabel("End Probe:"))
        probe_b_selector = QComboBox()
        probe_b_selector.addItems([f"Probe {p+1}" for p in range(self.probe_count)])
        probe_b_selector.setCurrentIndex(1 if chrono_id == 0 else ((chrono_id * 2 + 1) % self.probe_count))
        probe_b_layout.addWidget(probe_b_selector)
        selection_layout.addLayout(probe_b_layout)
        
        layout.addLayout(selection_layout)
        
        # Time display
        display_layout = QHBoxLayout()
        
        time_label = QLabel("Time:")
        time_label.setFont(QFont("Arial", 14))
        time_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        display_layout.addWidget(time_label)
        
        time_display = QLabel("0.0000")
        time_display.setFont(QFont("Courier", 36, QFont.Weight.Bold))
        time_display.setAlignment(Qt.AlignmentFlag.AlignCenter)
        time_display.setFrameShape(QFrame.Shape.StyledPanel)
        time_display.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        time_display.setMinimumHeight(80)
        display_layout.addWidget(time_display, 3)
        
        units_label = QLabel("seconds")
        units_label.setFont(QFont("Arial", 14))
        units_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        display_layout.addWidget(units_label)
        
        layout.addLayout(display_layout)
        
        # Reset button
        reset_button = QPushButton("Reset Measurement")
        reset_button.setFont(QFont("Arial", 10))
        
        layout.addWidget(reset_button)
        
        # Connect signals after all UI elements are created
        def update_probes():
            probe_a_idx = probe_a_selector.currentIndex()
            probe_b_idx = probe_b_selector.currentIndex()
            self.configure_specific_average_mode(chrono_id, probe_a_idx, probe_b_idx)
        
        probe_a_selector.currentIndexChanged.connect(update_probes)
        probe_b_selector.currentIndexChanged.connect(update_probes)
        
        reset_button.clicked.connect(lambda: self.reset_specific_average(
            chrono_id, 
            probe_a_selector.currentIndex(), 
            probe_b_selector.currentIndex()
        ))
        
        # Store references to the widgets
        chronometer = {
            'frame': frame,
            'probe_a_selector': probe_a_selector,
            'probe_b_selector': probe_b_selector,
            'time_display': time_display,
            'reset_button': reset_button
        }
        
        # Initial configuration only if we have enough probes
        if self.probe_count >= 2:
            update_probes()
        
        return chronometer
    
    def update_average_chronometers(self):
        # Check if we have enough probes for average mode
        if self.probe_count < 2:
            # Not enough probes - hide scroll area and show message
            self.not_enough_probes_message.setVisible(True)
            self.average_scroll_area.setVisible(False)
            
            # Clear existing chronometers to prevent errors
            for chrono in self.average_chronometers:
                chrono['frame'].setParent(None)
            self.average_chronometers.clear()
            return
            
        # We have enough probes - hide message and show scroll area
        self.not_enough_probes_message.setVisible(False)
        self.average_scroll_area.setVisible(True)
        
        # Clear existing chronometers
        for chrono in self.average_chronometers:
            chrono['frame'].setParent(None)
        
        self.average_chronometers.clear()
        
        # Calculate how many chronometers we can create
        # In average mode, each chronometer needs 2 probes
        max_chronos = max(1, self.probe_count // 2)
        
        # Add chronometers at the beginning of the layout (before the stretch)
        for i in range(max_chronos):
            chrono = self.create_average_chronometer(i)
            # Insert before the stretch
            self.average_layout.insertWidget(i, chrono['frame'])
            self.average_chronometers.append(chrono)
    
    def configure_specific_average_mode(self, chrono_id, probe_a_idx, probe_b_idx):
        # Only send the command if both indices are valid
        if 0 <= probe_a_idx < 256 and 0 <= probe_b_idx < 256 and 0 <= chrono_id < 256:
            # Command format: CONFIGURE_AVERAGE_MODE + chronometer_id + probe_a + probe_b
            self.send_command(CONFIGURE_AVERAGE_MODE + bytes([chrono_id, probe_a_idx, probe_b_idx]))
    
    def reset_specific_average(self, chrono_id, probe_a_idx, probe_b_idx):
        if 0 <= probe_a_idx < self.probe_count:
            self.send_command(RESET_PROBE_COMMAND + bytes([probe_a_idx]))
        if 0 <= probe_b_idx < self.probe_count:
            self.send_command(RESET_PROBE_COMMAND + bytes([probe_b_idx]))
    
    def update_mode_availability(self):
        # Disable average mode if we don't have enough probes
        if self.probe_count < 2:
            # If currently in average mode, switch to instantaneous
            if self.pages.currentIndex() == 1:
                self.instantaneous_radio.setChecked(True)
                self.pages.setCurrentIndex(0)
            
            # Disable average mode radio button
            self.average_radio.setEnabled(False)
            self.average_radio.setToolTip("Average mode requires at least 2 probes")
        else:
            # Enable average mode radio button
            self.average_radio.setEnabled(True)
            self.average_radio.setToolTip("")
    
    def switch_mode(self, button):
        # Check if we have enough probes for average mode
        if self.mode_button_group.id(button) == 1 and self.probe_count < 2:
            QMessageBox.warning(
                self,
                "Not Enough Probes",
                "Average speed measurement requires at least 2 probes.\n"
                "Please configure more probes in the Probe Configuration section."
            )
            self.instantaneous_radio.setChecked(True)
            return
            
        index = self.mode_button_group.id(button)
        self.pages.setCurrentIndex(index)
        
        if index == 1:  # Average mode
            # Configure all average chronometers
            for i, chrono in enumerate(self.average_chronometers):
                probe_a_idx = chrono['probe_a_selector'].currentIndex()
                probe_b_idx = chrono['probe_b_selector'].currentIndex()
                self.configure_specific_average_mode(i, probe_a_idx, probe_b_idx)
    
    def update_probe_count(self, count):
        self.probe_count = count
        
        # Update visibility of probe frames in instantaneous mode
        for probe_id, frame in self.probe_frames.items():
            frame.setVisible(probe_id < count)
        
        # Update mode availability
        self.update_mode_availability()
        
        # Update average chronometers
        self.update_average_chronometers()
    
    def apply_probe_configuration(self):
        # Send configuration command to the microcontroller
        self.send_command(CONFIGURE_PROBE_COUNT + bytes([self.probe_count]))
        
        # Update the UI to match the new configuration
        # Update dropdown in average mode selectors
        for chrono in self.average_chronometers:
            # Remember current selections
            current_a = chrono['probe_a_selector'].currentIndex()
            current_b = chrono['probe_b_selector'].currentIndex()
            
            # Update the items
            chrono['probe_a_selector'].clear()
            chrono['probe_b_selector'].clear()
            
            chrono['probe_a_selector'].addItems([f"Probe {p+1}" for p in range(self.probe_count)])
            chrono['probe_b_selector'].addItems([f"Probe {p+1}" for p in range(self.probe_count)])
            
            # Restore selections if possible, otherwise use defaults
            if current_a < self.probe_count:
                chrono['probe_a_selector'].setCurrentIndex(current_a)
            if current_b < self.probe_count:
                chrono['probe_b_selector'].setCurrentIndex(current_b)
    
    def reset_all_chronometers(self):
        # Reset all probes
        for probe_id in range(self.probe_count):
            self.send_command(RESET_PROBE_COMMAND + bytes([probe_id]))
    
    def init_serial(self):
        self.serial.setBaudRate(115200)
        self.serial.readyRead.connect(self.read_serial_data)
    
    def connect_serial(self):
        if self.serial.isOpen():
            self.serial.close()
            self.connect_button.setText("Connect")
            return
        
        selected_port = self.port_dropdown.currentText()
        if selected_port:
            self.serial.setPortName(selected_port)
            if self.serial.open(QIODevice.OpenModeFlag.ReadWrite):
                print(f"Connected to {selected_port}")
                self.connect_button.setText("Disconnect")
                
                # Send the initial probe count configuration
                self.apply_probe_configuration()
            else:
                print("Failed to open serial port.")
    
    def refresh_ports(self):
        current_port = self.port_dropdown.currentText()
        self.port_dropdown.clear()
        ports = QSerialPortInfo.availablePorts()
        for port in ports:
            self.port_dropdown.addItem(port.portName())
        
        # Try to restore the previously selected port if it still exists
        index = self.port_dropdown.findText(current_port)
        if index >= 0:
            self.port_dropdown.setCurrentIndex(index)
    
    def send_command(self, command: bytes):
        if self.serial.isOpen():
            print(f"Sending: {command + END_PACKET_DELIMITER}")
            self.serial.write(command + END_PACKET_DELIMITER)
    
    def read_serial_data(self):
        self.serial_buffer += self.serial.readAll().data()
        while END_PACKET_DELIMITER in self.serial_buffer:
            pkt, self.serial_buffer = self.serial_buffer.split(END_PACKET_DELIMITER, 1)
            print(f"Received: {pkt}")
            
            if pkt.startswith(REQUEST_AVERAGE_UPDATE):
                # Format: A + chronometer_id + time_value(4 bytes)
                if len(pkt) >= 6:  # 1 byte command + 1 byte chrono_id + 4 bytes time
                    chrono_id, average_time = struct.unpack('<BL', pkt[1:6])
                    self.update_specific_average_display(chrono_id, average_time)
            elif pkt.startswith(REQUEST_PROBE_UPDATE):
                # Format: U + probe_id + pulse_time(4 bytes)
                if len(pkt) >= 6:  # 1 byte command + 1 byte probe_id + 4 bytes time
                    probe_id, pulse_time = struct.unpack('<BL', pkt[1:6])
                    self.update_instantaneous_display(probe_id, pulse_time)
    
    def update_specific_average_display(self, chrono_id, average_time):
        if chrono_id < len(self.average_chronometers):
            self.average_chronometers[chrono_id]['time_display'].setText(f"{average_time*1e-6:.4f}")
    
    def update_instantaneous_display(self, probe_id, pulse_time):
        if probe_id in self.time_displays:
            self.time_displays[probe_id].setText(f"{pulse_time*1e-6:.4f}")
    
    def init_timer(self):
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.poll_current_mode)
        self.timer.start(200)
    
    def poll_current_mode(self):
        if not self.serial.isOpen():
            return
            
        if self.pages.currentIndex() == 0:  # Instantaneous mode
            # Only poll active probes
            for probe_id in range(self.probe_count):
                self.send_command(REQUEST_PROBE_UPDATE + bytes([probe_id]))
        elif self.pages.currentIndex() == 1:  # Average mode
            # Poll each chronometer
            for i in range(len(self.average_chronometers)):
                self.send_command(REQUEST_AVERAGE_UPDATE + bytes([i]))
    
    def resizeEvent(self, event):
        # This event handler is called when the widget is resized
        super().resizeEvent(event)
        
        # Adjust font sizes based on window size
        width = self.width()
        # Scale fonts proportionally to window width
        if width > 1200:
            display_font_size = 48
            label_font_size = 20
        elif width > 800:
            display_font_size = 42
            label_font_size = 16
        elif width > 600:
            display_font_size = 32
            label_font_size = 14
        else:
            display_font_size = 24
            label_font_size = 12
            
        # Update font sizes for time displays
        for display in self.time_displays.values():
            font = display.font()
            font.setPointSize(display_font_size)
            display.setFont(font)
            
        # Update average display fonts
        for chrono in self.average_chronometers:
            font = chrono['time_display'].font()
            font.setPointSize(display_font_size)
            chrono['time_display'].setFont(font)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = StopwatchUI()
    window.show()
    sys.exit(app.exec())