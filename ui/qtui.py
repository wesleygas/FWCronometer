import sys
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QPushButton, QLabel, QComboBox, QStackedWidget, 
    QHBoxLayout, QRadioButton, QButtonGroup, QSizePolicy, QSpacerItem, QFrame, QGridLayout
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

class BarrierProbe():
    def __init__(self, id):
        self.id = id
        self.pulse_time = 0

class StopwatchUI(QWidget):
    def __init__(self):
        super().__init__()
        self.probes = {i: BarrierProbe(i) for i in range(2)}  # Support for multiple probes
        self.selected_probe_a = 0
        self.selected_probe_b = 1
        self.init_ui()
        self.init_serial()
        self.init_timer()
        self.serial_buffer = b''
        
    def init_ui(self):
        self.setWindowTitle("Physics Class Timer")
        self.setGeometry(200, 200, 800, 600)
        self.main_layout = QVBoxLayout()
        self.main_layout.setSpacing(20)
        self.main_layout.setContentsMargins(20, 20, 20, 20)
        
        # Top section with connection controls and mode selection
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
        
        # Add both groups to the top section
        top_section.addWidget(connection_group, 1)
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
    
    def create_instantaneous_page(self):
        page = QWidget()
        layout = QVBoxLayout()
        layout.setSpacing(20)
        
        # Title
        title = QLabel("Instantaneous Speed Measurement")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setFont(QFont("Arial", 14, QFont.Weight.Bold))
        layout.addWidget(title)
        
        # Time displays with labels
        display_frame = QFrame()
        display_frame.setFrameShape(QFrame.Shape.StyledPanel)
        display_layout = QGridLayout(display_frame)
        display_layout.setSpacing(15)
        
        self.time_displays = {}
        self.reset_buttons = {}
        
        row = 0
        for probe_id in self.probes:
            # Label for the probe
            probe_label = QLabel(f"Probe {probe_id+1}:")
            probe_label.setFont(QFont("Arial", 12, QFont.Weight.Bold))
            probe_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            display_layout.addWidget(probe_label, row, 0)
            
            # Time display
            time_display = QLabel("0.0000")
            time_display.setFont(QFont("Courier", 36, QFont.Weight.Bold))
            time_display.setAlignment(Qt.AlignmentFlag.AlignCenter)
            time_display.setFrameShape(QFrame.Shape.StyledPanel)
            time_display.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
            time_display.setMinimumHeight(100)
            self.time_displays[probe_id] = time_display
            display_layout.addWidget(time_display, row, 1)
            
            # Units label
            units_label = QLabel("seconds")
            units_label.setFont(QFont("Arial", 12))
            units_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            display_layout.addWidget(units_label, row, 2)
            
            # Reset button
            button = QPushButton(f"Reset Probe {probe_id+1}")
            button.setFont(QFont("Arial", 10))
            button.clicked.connect(lambda _, pid=probe_id: self.send_command(RESET_PROBE_COMMAND + bytes([pid])))
            self.reset_buttons[probe_id] = button
            display_layout.addWidget(button, row, 3)
            
            row += 1
        
        display_layout.setColumnStretch(0, 1)  # Probe label
        display_layout.setColumnStretch(1, 3)  # Time display
        display_layout.setColumnStretch(2, 1)  # Units
        display_layout.setColumnStretch(3, 1)  # Reset button
        
        layout.addWidget(display_frame, 1)
        
        # Add explanation at the bottom
        explanation = QLabel("Measures the time it takes for an object to pass through a single sensor.")
        explanation.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(explanation)
        
        page.setLayout(layout)
        return page
    
    def create_average_page(self):
        page = QWidget()
        layout = QVBoxLayout()
        layout.setSpacing(20)
        
        # Title
        title = QLabel("Average Speed Measurement")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setFont(QFont("Arial", 14, QFont.Weight.Bold))
        layout.addWidget(title)
        
        # Probe selection
        selection_frame = QFrame()
        selection_frame.setFrameShape(QFrame.Shape.StyledPanel)
        selection_layout = QHBoxLayout(selection_frame)
        
        # Probe A selection
        probe_a_layout = QVBoxLayout()
        probe_a_layout.addWidget(QLabel("Start Probe:"))
        self.probe_a_selector = QComboBox()
        self.probe_a_selector.addItems([f"Probe {p+1}" for p in self.probes])
        self.probe_a_selector.setCurrentIndex(0)
        self.probe_a_selector.currentIndexChanged.connect(self.update_probe_selection)
        probe_a_layout.addWidget(self.probe_a_selector)
        selection_layout.addLayout(probe_a_layout)
        
        # Probe B selection
        probe_b_layout = QVBoxLayout()
        probe_b_layout.addWidget(QLabel("End Probe:"))
        self.probe_b_selector = QComboBox()
        self.probe_b_selector.addItems([f"Probe {p+1}" for p in self.probes])
        self.probe_b_selector.setCurrentIndex(1)
        self.probe_b_selector.currentIndexChanged.connect(self.update_probe_selection)
        probe_b_layout.addWidget(self.probe_b_selector)
        selection_layout.addLayout(probe_b_layout)
        
        layout.addWidget(selection_frame)
        
        # Time display
        display_frame = QFrame()
        display_frame.setFrameShape(QFrame.Shape.StyledPanel)
        display_layout = QHBoxLayout(display_frame)
        
        time_label = QLabel("Time:")
        time_label.setFont(QFont("Arial", 18, QFont.Weight.Bold))
        time_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        display_layout.addWidget(time_label)
        
        self.average_display = QLabel("0.0000")
        self.average_display.setFont(QFont("Courier", 48, QFont.Weight.Bold))
        self.average_display.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.average_display.setFrameShape(QFrame.Shape.StyledPanel)
        self.average_display.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.average_display.setMinimumHeight(150)
        display_layout.addWidget(self.average_display, 3)
        
        units_label = QLabel("seconds")
        units_label.setFont(QFont("Arial", 18))
        units_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        display_layout.addWidget(units_label)
        
        layout.addWidget(display_frame, 1)
        
        # Reset button
        self.reset_average_button = QPushButton("Reset Measurement")
        self.reset_average_button.setFont(QFont("Arial", 12))
        self.reset_average_button.clicked.connect(self.reset_average_selected_probes)
        layout.addWidget(self.reset_average_button)
        
        # Add explanation at the bottom
        explanation = QLabel("Measures the time it takes for an object to travel between two sensors.")
        explanation.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(explanation)
        
        page.setLayout(layout)
        return page
    
    def switch_mode(self, button):
        index = self.mode_button_group.id(button)
        self.pages.setCurrentIndex(index)
        if index == 1:
            self.configure_average_mode()

    def reset_average_selected_probes(self):
        probe_a_idx = self.probe_a_selector.currentIndex()
        probe_b_idx = self.probe_b_selector.currentIndex()
        self.send_command(RESET_PROBE_COMMAND + bytes([probe_a_idx]))
        self.send_command(RESET_PROBE_COMMAND + bytes([probe_b_idx]))
    
    def update_probe_selection(self):
        probe_a_name = self.probe_a_selector.currentText()
        probe_b_name = self.probe_b_selector.currentText()
        self.selected_probe_a = int(probe_a_name[-1]) - 1  # Extract the probe number (1-based) and convert to 0-based
        self.selected_probe_b = int(probe_b_name[-1]) - 1
        self.configure_average_mode()
    
    def configure_average_mode(self):
        self.send_command(CONFIGURE_AVERAGE_MODE + bytes([self.selected_probe_a, self.selected_probe_b]))
    
    def init_serial(self):
        self.serial = QSerialPort()
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
            self.serial.write(command + END_PACKET_DELIMITER)
    
    def read_serial_data(self):
        self.serial_buffer += self.serial.readAll().data()
        while END_PACKET_DELIMITER in self.serial_buffer:
            pkt, self.serial_buffer = self.serial_buffer.split(END_PACKET_DELIMITER, 1)
            print(pkt)
            if pkt.startswith(REQUEST_AVERAGE_UPDATE):
                average_time = struct.unpack('<L', pkt[1:])[0]
                self.update_average_display(average_time)
            elif pkt.startswith(REQUEST_PROBE_UPDATE):
                probe_id, pulse_time = struct.unpack('<BL', pkt[1:])
                self.update_instantaneous_display(probe_id, pulse_time)
    
    def update_average_display(self, average_time):
        self.average_display.setText(f"{average_time*1e-6:.4f}")
    
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
            
        if self.pages.currentIndex() == 0:
            for probe_id in self.probes:
                self.send_command(REQUEST_PROBE_UPDATE + bytes([probe_id]))
        elif self.pages.currentIndex() == 1:
            self.send_command(REQUEST_AVERAGE_UPDATE)
    
    def resizeEvent(self, event):
        # This event handler is called when the widget is resized
        super().resizeEvent(event)
        
        # Adjust font sizes based on window size
        width = self.width()
        # Scale fonts proportionally to window width
        if width > 1200:
            display_font_size = 54
            label_font_size = 20
        elif width > 800:
            display_font_size = 48
            label_font_size = 16
        elif width > 600:
            display_font_size = 36
            label_font_size = 14
        else:
            display_font_size = 28
            label_font_size = 12
            
        # Update font sizes for time displays
        for display in self.time_displays.values():
            font = display.font()
            font.setPointSize(display_font_size)
            display.setFont(font)
            
        # Update average display font
        font = self.average_display.font()
        font.setPointSize(display_font_size)
        self.average_display.setFont(font)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = StopwatchUI()
    window.show()
    sys.exit(app.exec())