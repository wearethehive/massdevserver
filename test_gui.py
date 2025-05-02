# Test file for GUI functionality
from PySide6.QtWidgets import QApplication, QMainWindow, QLabel
import sys

def main():
    app = QApplication(sys.argv)
    window = QMainWindow()
    window.setWindowTitle('Test GUI')
    window.setGeometry(100, 100, 200, 100)
    
    label = QLabel('GUI Test Successful!', window)
    label.setGeometry(50, 40, 150, 20)
    
    window.show()
    return app.exec()

if __name__ == '__main__':
    sys.exit(main()) 