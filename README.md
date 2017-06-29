# digikey-po-gen
Generates a purchase order for digikey finding the lowest price break and optionally only digireels/tape&amp;reel

## example
/digikey-po-gen.py --bom BOM.csv --partlist Parts.csv --out digikey.csv --url www.digikey.ca --qty 100 --reels --digireel_cost 8.5

BOM contains a list of internal part numbers and quantities.
Parts contains a mapping of internal part numbers to manufacturer part numbers.
If "--reels" is included, either a digireel or tape&amp;reel will be add to the PO, whichever is less expensive.

Dependency:
* Python 3
* Beautiful Soup (`pip install beautifulsoup4`)
