param(
    [string]$ProjectRoot = "$(Split-Path -Parent $PSScriptRoot)"
)
Set-Location $ProjectRoot
python -m pip install --upgrade pip
python -m pip install customtkinter requests cryptography psutil pystray Pillow win10toast pyinstaller
pyinstaller --noconfirm --onefile --noconsole --name CampusLogin `
  "Original_Python_Project/campus_login_optimized.pyw" `
  --hidden-import customtkinter --hidden-import pystray --hidden-import PIL --hidden-import win10toast --hidden-import psutil --hidden-import cryptography
