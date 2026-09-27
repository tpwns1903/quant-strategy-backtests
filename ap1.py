from tiingo import TiingoClient
import pandas as pd
import keyring
import win32

api_key = keyring.get_password('tiingo', 'sejunkim')
config = {}
config['session'] = True
config['api_key'] = api_key
client = TiingoClient(config)

tickers = client.list_stock_tickers()
tickers_df =pd.DataFrame.from_records(tickers)

tickers_df.head()

