#!/bin/sh
set -e

echo "Starte Task 1"
python -m ebAlert links -a "https://www.kleinanzeigen.de/s-pc-zubehoer-software/grafikkarten,mainboards,prozessor_cpu,sonstiges,speicher/c225+pc_zubehoer_software.art_s:(grafikkarten%2Cmainboards%2Cprozessor_cpu%2Csonstiges%2Cspeicher)"
python -m ebAlert links -a "https://www.kleinanzeigen.de/s-handy-telekom/preis::420/c173"
python -m ebAlert links -a "https://www.kleinanzeigen.de/s-ryzen/k0"
echo "Starte Task 2"
python -m ebAlert start

echo "Alle Tasks fertig"
