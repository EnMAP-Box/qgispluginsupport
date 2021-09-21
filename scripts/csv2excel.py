import csv
import pathlib
import os
csv_dir = pathlib.Path('/data/Jakku/diss_bj/csvtests')
csv_dir = pathlib.Path('~').expanduser() / 'Downloads' / 'csvtests'
os.makedirs(csv_dir, exist_ok=True)

pathA = csv_dir / 'A.csv'
pathB = csv_dir / 'B.csv'
with open(pathA, 'w', newline='') as csvfile:
    spamwriter = csv.writer(csvfile, delimiter=';',
        quotechar='|', quoting=csv.QUOTE_MINIMAL)
    spamwriter.writerow(['Spam'] * 5 + ['Baked Beans'])
    spamwriter.writerow(['Spam', 'Lovely Spam', 'Wonderful Spam'])
    spamwriter.writerow(['1.46', 1.46])

with open(pathB, 'w', newline='') as csvfile:
    spamwriter = csv.writer(csvfile, dialect=csv.excel)
    spamwriter.writerow(['Spam'] * 5 + ['Baked Beans'])
    spamwriter.writerow(['Spam', 'Lovely Spam', 'Wonderful Spam'])
    spamwriter.writerow(['1.46', 1.46])

