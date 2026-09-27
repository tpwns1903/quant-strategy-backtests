import os
import keyring
import win32api, win32, win32timezone

# Tiingo API 키는 코드에 직접 쓰지 않고 환경변수 TIINGO_API_KEY 로 전달한다.
keyring.set_password('tiingo', 'sejunkim', os.environ['TIINGO_API_KEY'])
#keyring.core.set_keyring(keyring.core.load_keyring('keyring.backends.Windows.WinVaultKeyring'))