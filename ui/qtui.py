import sys
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QPushButton, QLabel, QComboBox, QStackedWidget, 
    QHBoxLayout, QRadioButton, QButtonGroup, QSizePolicy, QSpacerItem, QFrame, QGridLayout,
    QScrollArea
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
REQUEST_PROBE_COUNT = b'Pcnt'

class BarrierProbe():
    def __init__(self, id):
        self.id = id
        self.pulse_time = 0

class StopwatchUI(QWidget):
    def __init__(self):
        super().__init__()
        self.probes = {}  # Will be populated after querying the number of probes
        self.probe_count = 0  # Will be set after connecting and querying
        self.active_average_pairs = []  # Tracks active probe pairs for average mode
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
        
        # Status label for probe count
        self.status_label = QLabel("Not connected")
        connection_layout.addWidget(self.status_label)
        
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
        
        # Reset All button
        self.reset_all_button = QPushButton("Reset All Chronometers")
        self.reset_all_button.setFont(QFont("Arial", 10, QFont.Weight.Bold))
        self.reset_all_button.clicked.connect(self.reset_all_probes)
        self.reset_all_button.setEnabled(False)  # Disabled until connected
        mode_layout.addWidget(self.reset_all_button)
        
        # Add both groups to the top section
        top_section.addWidget(connection_group, 1)
        top_section.addWidget(mode_group, 1)
        
        # Add top section to main layout
        self.main_layout.addLayout(top_section)
        
        # Page Container
        self.pages = QStackedWidget()
        
        # Create placeholder pages - will be populated after getting probe count
        self.instantaneous_page = QWidget()
        self.average_page = QWidget()
        
        self.pages.addWidget(self.instantaneous_page)
        self.pages.addWidget(self.average_page)
        self.main_layout.addWidget(self.pages, 1)  # Give it a stretch factor for resizing
        
        self.setLayout(self.main_layout)
    
    def create_instantaneous_page(self):
        # Create a new page with scrollable area to accommodate many probes
        page = QWidget()
        main_layout = QVBoxLayout(page)
        main_layout.setSpacing(20)
        
        # Title
        title = QLabel("Instantaneous Speed Measurement")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setFont(QFont("Arial", 14, QFont.Weight.Bold))
        main_layout.addWidget(title)
        
        # Scrollable area for chronometers
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        
        scroll_content = QWidget()
        scroll_layout = QVBoxLayout(scroll_content)
        scroll_layout.setSpacing(15)
        
        # Time displays with labels
        self.time_displays = {}
        self.reset_buttons = {}
        
        for probe_id in range(self.probe_count):
            display_frame = QFrame()
            display_frame.setFrameShape(QFrame.Shape.StyledPanel)
            display_layout = QGridLayout(display_frame)
            display_layout.setSpacing(10)
            
            # Label for the probe
            probe_label = QLabel(f"Probe {probe_id+1}:")
            probe_label.setFont(QFont("Arial", 12, QFont.Weight.Bold))
            probe_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            display_layout.addWidget(probe_label, 0, 0)
            
            # Time display
            time_display = QLabel("0.0000")
            time_display.setFont(QFont("Courier", 36, QFont.Weight.Bold))
            time_display.setAlignment(Qt.AlignmentFlag.AlignCenter)
            time_display.setFrameShape(QFrame.Shape.StyledPanel)
            time_display.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            time_display.setMinimumHeight(80)
            self.time_displays[probe_id] = time_display
            display_layout.addWidget(time_display, 0, 1)
            
            # Units label
            units_label = QLabel("seconds")
            units_label.setFont(QFont("Arial", 12))
            units_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            display_layout.addWidget(units_label, 0, 2)
            
            # Reset button
            button = QPushButton(f"Reset")
            button.setFont(QFont("Arial", 10))
            button.clicked.connect(lambda _, pid=probe_id: self.send_command(RESET_PROBE_COMMAND + bytes([pid])))
            self.reset_buttons[probe_id] = button
            display_layout.addWidget(button, 0, 3)
            
            display_layout.setColumnStretch(0, 1)  # Probe label
            display_layout.setColumnStretch(1, 3)  # Time display
            display_layout.setColumnStretch(2, 1)  # Units
            display_layout.setColumnStretch(3, 1)  # Reset button
            
            scroll_layout.addWidget(display_frame)
        
        scroll_area.setWidget(scroll_content)
        main_layout.addWidget(scroll_area, 1)
        
        # Add explanation at the bottom
        explanation = QLabel("Measures the time it takes for an object to pass through a single sensor.")
        explanation.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(explanation)
        
        return page
    
    def create_average_page(self):
        page = QWidget()
        main_layout = QVBoxLayout(page)
        main_layout.setSpacing(20)
        
        # Title
        title = QLabel("Average Speed Measurement")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setFont(QFont("Arial", 14, QFont.Weight.Bold))
        main_layout.addWidget(title)
        
        # Scrollable area for chronometer pairs
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        
        scroll_content = QWidget()
        self.average_layout = QVBoxLayout(scroll_content)
        self.average_layout.setSpacing(20)
        
        if self.probe_count >= 2:
            # Add first pair controls
            self.add_average_pair_controls()
            
            # Add button for adding more chronometer pairs if there are enough probes
            if self.probe_count > 2:
                self.add_pair_button = QPushButton("Add Chronometer Pair")
                self.add_pair_button.clicked.connect(self.add_average_pair_controls)
                self.average_layout.addWidget(self.add_pair_button)
        else:
            not_enough_label = QLabel("At least 2 probes are required for average speed measurement.")
            not_enough_label.setFont(QFont("Arial", 12))
            not_enough_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.average_layout.addWidget(not_enough_label)
        
        scroll_area.setWidget(scroll_content)
        main_layout.addWidget(scroll_area, 1)
        
        # Add explanation at the bottom
        explanation = QLabel("Measures the time it takes for an object to travel between two sensors.")
        explanation.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(explanation)
        
        return page
    
    def add_average_pair_controls(self):
        # Create a control set for an average measurement between two probes
        if len(self.active_average_pairs) >= self.probe_count // 2:
            # No more pairs can be added
            return
            
        pair_frame = QFrame()
        pair_frame.setFrameShape(QFrame.Shape.StyledPanel)
        pair_layout = QVBoxLayout(pair_frame)
        
        # Probe selection
        selection_layout = QHBoxLayout()
        
        # Find available probes (not already used in other pairs)
        used_probes = []
        for pair in self.active_average_pairs:
            used_probes.extend([pair['probe_a'], pair['probe_b']])
        
        available_probes = [i for i in range(self.probe_count) if i not in used_probes]
        
        if len(available_probes) < 2:
            # Not enough probes available
            return
            
        # Probe A selection
        probe_a_layout = QVBoxLayout()
        probe_a_layout.addWidget(QLabel("Start Probe:"))
        probe_a_selector = QComboBox()
        for p in available_probes:
            probe_a_selector.addItem(f"Probe {p+1}", p)
        selection_layout.addLayout(probe_a_layout)
        selection_layout.addWidget(probe_a_selector)
        
        # Probe B selection
        probe_b_layout = QVBoxLayout()
        probe_b_layout.addWidget(QLabel("End Probe:"))
        probe_b_selector = QComboBox()
        # Initially, add all probes except the one selected in A
        first_probe = probe_a_selector.currentData()
        for p in available_probes:
            if p != first_probe:
                probe_b_selector.addItem(f"Probe {p+1}", p)
        selection_layout.addLayout(probe_b_layout)
        selection_layout.addWidget(probe_b_selector)
        
        pair_layout.addLayout(selection_layout)
        
        # Update probe B options when probe A changes
        def update_probe_b_options():
            probe_b_selector.clear()
            selected_a = probe_a_selector.currentData()
            for p in available_probes:
                if p != selected_a:
                    probe_b_selector.addItem(f"Probe {p+1}", p)
        
        probe_a_selector.currentIndexChanged.connect(update_probe_b_options)
        
        # Time display
        display_layout = QHBoxLayout()
        
        time_label = QLabel("Time:")
        time_label.setFont(QFont("Arial", 14, QFont.Weight.Bold))
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
        
        pair_layout.addLayout(display_layout)
        
        # Reset and remove buttons
        button_layout = QHBoxLayout()
        
        reset_button = QPushButton("Reset Measurement")
        reset_button.setFont(QFont("Arial", 10))
        button_layout.addWidget(reset_button)
        
        remove_button = QPushButton("Remove")
        remove_button.setFont(QFont("Arial", 10))
        button_layout.addWidget(remove_button)
        
        pair_layout.addLayout(button_layout)
        
        # Add to layout
        self.average_layout.insertWidget(len(self.active_average_pairs), pair_frame)
        
        # Create data structure for this pair
        pair_data = {
            'frame': pair_frame,
            'probe_a': probe_a_selector.currentData(),
            'probe_b': probe_b_selector.currentData(),
            'probe_a_selector': probe_a_selector,
            'probe_b_selector': probe_b_selector,
            'time_display': time_display,
            'reset_button': reset_button,
            'remove_button': remove_button
        }
        
        self.active_average_pairs.append(pair_data)
        
        # Connect signals
        def update_pair_config():
            pair_data['probe_a'] = probe_a_selector.currentData()
            pair_data['probe_b'] = probe_b_selector.currentData()
            self.configure_average_pairs()
        
        probe_a_selector.currentIndexChanged.connect(update_pair_config)
        probe_b_selector.currentIndexChanged.connect(update_pair_config)
        
        reset_button.clicked.connect(lambda: self.reset_average_pair(pair_data))
        
        # Remove button action
        def remove_pair():
            self.active_average_pairs.remove(pair_data)
            pair_frame.deleteLater()
            self.configure_average_pairs()
            # Re-enable the add button if needed
            if hasattr(self, 'add_pair_button') and len(self.active_average_pairs) < self.probe_count // 2:
                self.add_pair_button.setEnabled(True)
        
        remove_button.clicked.connect(remove_pair)
        
        # Configure the pair
        self.configure_average_pairs()
        
        # Update add button state
        if hasattr(self, 'add_pair_button'):
            self.add_pair_button.setEnabled(len(self.active_average_pairs) < self.probe_count // 2)
    
    def reset_average_pair(self, pair_data):
        self.send_command(RESET_PROBE_COMMAND + bytes([pair_data['probe_a']]))
        self.send_command(RESET_PROBE_COMMAND + bytes([pair_data['probe_b']]))
    
    def configure_average_pairs(self):
        # Send configuration for all active pairs
        for i, pair in enumerate(self.active_average_pairs):
            cmd = CONFIGURE_AVERAGE_MODE + bytes([pair['probe_a'], pair['probe_b'], i])  # Add pair index
            self.send_command(cmd)
    
    def switch_mode(self, button):
        index = self.mode_button_group.id(button)
        self.pages.setCurrentIndex(index)
        if index == 1:
            self.configure_average_pairs()
    
    def reset_all_probes(self):
        # Reset all probes
        for probe_id in range(self.probe_count):
            self.send_command(RESET_PROBE_COMMAND + bytes([probe_id]))
    
    def init_serial(self):
        self.serial = QSerialPort()
        self.serial.setBaudRate(115200)
        self.serial.readyRead.connect(self.read_serial_data)
    
    def connect_serial(self):
        if self.serial.isOpen():
            self.serial.close()
            self.connect_button.setText("Connect")
            self.status_label.setText("Not connected")
            self.reset_all_button.setEnabled(False)
            return
        
        selected_port = self.port_dropdown.currentText()
        if selected_port:
            self.serial.setPortName(selected_port)
            if self.serial.open(QIODevice.OpenModeFlag.ReadWrite):
                print(f"Connected to {selected_port}")
                self.connect_button.setText("Disconnect")
                self.status_label.setText("Connected - Querying probes...")
                
                # Query the number of available probes
                self.send_command(REQUEST_PROBE_COUNT)
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
            print(f"Received packet: {pkt}")
            
            if pkt.startswith(REQUEST_PROBE_COUNT):
                # Format is REQUEST_PROBE_COUNT + single byte with count
                count = pkt[len(REQUEST_PROBE_COUNT)]
                self.handle_probe_count_response(count)
            elif pkt.startswith(REQUEST_AVERAGE_UPDATE):
                # Format is REQUEST_AVERAGE_UPDATE + pair_index (1 byte) + time (4 bytes)
                pair_index = pkt[1]
                average_time = struct.unpack('<L', pkt[2:])[0]
                self.update_average_display(pair_index, average_time)
            elif pkt.startswith(REQUEST_PROBE_UPDATE):
                # Format is REQUEST_PROBE_UPDATE + probe_id (1 byte) + time (4 bytes)
                probe_id, pulse_time = struct.unpack('<BL', pkt[1:])
                self.update_instantaneous_display(probe_id, pulse_time)
    
    def handle_probe_count_response(self, count):
        print(f"Detected {count} probes")
        self.probe_count = count
        self.status_label.setText(f"Connected - {count} probes detected")
        self.reset_all_button.setEnabled(True)
        
        # Initialize probes dictionary
        self.probes = {i: BarrierProbe(i) for i in range(count)}
        
        # Create UI pages based on probe count
        self.recreate_pages()
    
    def recreate_pages(self):
        # Create new pages with proper probe count
        new_instantaneous_page = self.create_instantaneous_page()
        new_average_page = self.create_average_page()
        
        # Remove old pages and add new ones
        self.pages.removeWidget(self.instantaneous_page)
        self.pages.removeWidget(self.average_page)
        
        self.instantaneous_page = new_instantaneous_page
        self.average_page = new_average_page
        
        self.pages.insertWidget(0, self.instantaneous_page)
        self.pages.insertWidget(1, self.average_page)
        
        # Set current page based on the currently selected mode
        current_mode = 0 if self.instantaneous_radio.isChecked() else 1
        self.pages.setCurrentIndex(current_mode)
    
    def update_average_display(self, pair_index, average_time):
        if pair_index < len(self.active_average_pairs):
            self.active_average_pairs[pair_index]['time_display'].setText(f"{average_time*1e-6:.4f}")
    
    def update_instantaneous_display(self, probe_id, pulse_time):
        if probe_id in self.time_displays:
            self.time_displays[probe_id].setText(f"{pulse_time*1e-6:.4f}")
    
    def init_timer(self):
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.poll_current_mode)
        self.timer.start(200)
    
    def poll_current_mode(self):
        if not self.serial.isOpen() or self.probe_count == 0:
            return
            
        if self.pages.currentIndex() == 0:
            # Instantaneous mode
            for probe_id in range(self.probe_count):
                self.send_command(REQUEST_PROBE_UPDATE + bytes([probe_id]))
        elif self.pages.currentIndex() == 1:
            # Average mode
            for i in range(len(self.active_average_pairs)):
                self.send_command(REQUEST_AVERAGE_UPDATE + bytes([i]))
    
    def resizeEvent(self, event):
        # This event handler is called when the widget is resized
        super().resizeEvent(event)
        
        # Adjust font sizes based on window size
        width = self.width()
        # Scale fonts proportionally to window width
        if width > 1200:
            display_font_size = 42
            label_font_size = 18
        elif width > 800:
            display_font_size = 36
            label_font_size = 14
        elif width > 600:
            display_font_size = 30
            label_font_size = 12
        else:
            display_font_size = 24
            label_font_size = 10
            
        # Update font sizes for time displays in instantaneous mode
        if hasattr(self, 'time_displays'):
            for display in self.time_displays.values():
                font = display.font()
                font.setPointSize(display_font_size)
                display.setFont(font)
            
        # Update average display fonts
        if hasattr(self, 'active_average_pairs'):
            for pair in self.active_average_pairs:
                font = pair['time_display'].font()
                font.setPointSize(display_font_size)
                pair['time_display'].setFont(font)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = StopwatchUI()
    window.show()
    sys.exit(app.exec())