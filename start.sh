#!/bin/bash
set -e

echo "Starte Task 1"
python -m ebAlert links -a "https://www.kleinanzeigen.de/s-pc-zubehoer-software/speicher/c225+pc_zubehoer_software.art_s:speicher"

echo "Starte Task 2"
python -m ebAlert start

echo "Alle Tasks fertig"
