#!/usr/bin/env python3

import sys
import argparse
import csv
import urllib.request
import urllib.parse
from bs4 import BeautifulSoup

class DigikeySearch(object):
    
    def __init__(self, url):
        self.products = []
        self.keyword = ''
        self.url = 'www.' + url.replace('www.','')
        
    def handleQty(self, string):
        quantity = 0
        if string.isdecimal():
            quantity = int(string)
        elif ' - Immediate' in string:
            quantity = int(string.split(' ')[0].replace(',', ''))
        elif ' - Factory Stock' in string:
            quantity = 0
        elif 'Standard Lead Time' in string:
            quantity = 0
        else:
            print("Unknown format: ", string)
            
        return quantity        

    def process_table_(self, table):
        #search for manufacturer part number and get digikey pn for cuttape, digireel, tape&reel
        for product in table.findAll('tr',{'itemtype':'http://schema.org/Product'}):
#             print(product)
            productInfo = {}
            productInfo['dkPartNumber'] = product.find("td", class_="tr-dkPartNumber").get_text(strip=True)
            productInfo['mfgPartNumber'] = product.find("td", class_="tr-mfgPartNumber").get_text(strip=True)
            productInfo['vendor'] = product.find("td", class_="tr-vendor").get_text(strip=True)
            productInfo['description'] = product.find("td", class_="tr-description").get_text(strip=True)
            # handles '8,045 - Immediate'
            productInfo['qtyAvailable'] = self.handleQty(product.find("td", class_="tr-qtyAvailable").get_text(strip=True))
            # could be 'Digi-reels'
            productInfo['unitPrice'] = product.find("td", class_="tr-unitPrice").get_text(strip=True)
            productInfo['packaging'] = product.find("td", class_="tr-packaging").get_text(strip=True) if product.find("td", class_="tr-packaging") is not None else None
            self.products.append(productInfo)

    def fetch_pricing_(self):
        #search for each digikey part number to get the pricing
        for product in self.products:
            data = {'keywords':product['dkPartNumber']}
            params = urllib.parse.urlencode(data)
            url = "http://%s/product-search/en?%s" % (self.url, params)
            with urllib.request.urlopen(url) as f:
                soup = BeautifulSoup(f.read().decode('utf-8'), "lxml")
                table = soup.html.find('table', dict(id='product-dollars'))
                if table is not None:
                    pricing = []
                    for row in table.find_all('tr'):
                        cols = [ele.text.strip() for ele in row.find_all('td')]
                        if len(cols): #strip out comma as thousands separator
                            pricing.append([float(ele.replace(',','')) for ele in cols if ele])
                    product['pricing'] = pricing
        
    def search(self, keyword):
        self.keyword = keyword
        data = {'keywords':self.keyword}
        params = urllib.parse.urlencode(data)
        url = "http://%s/product-search/en?%s" % (self.url, params)
        with urllib.request.urlopen(url) as f:
            soup = BeautifulSoup(f.read().decode('utf-8'), "lxml")

        productTable = soup.html.find('table', dict(id='productTable')).find('tbody')
        self.process_table_(productTable)
        self.fetch_pricing_()
            
    def exact_matches(self):
        results = []
        for product in self.products:
            if product['mfgPartNumber'] == self.keyword:
                results.append(product)
        return results


def main(args):

    partList = {}
    #Header like Part Number,Description,Mfg1,Mpn1,Mfg2,Mpn2
    with open(args.list, newline='') as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            partList[row['Part Number']] = row

    bomList = {}
    #Header like Part Number,Description,Quantity,Designator,Mfg1,Mpn1,Mfg2,Mpn2
    with open(args.input, newline='') as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            bomList[row['Part Number']] = row

    digikeyCatalog = {}
    #Search digikey for each part in BOM
    for key, value in bomList.items():
        part = partList[key]
        for mfg, mpn in (('Mfg1', 'Mpn1'),('Mfg2','Mpn2')):
            if part[mfg] and part[mpn]:
                print("Fetching", key, part[mfg], part[mpn], "...", sep=' ', flush=True)
                search = DigikeySearch(args.digikey_url)
                search.search(part[mpn])
                results = search.exact_matches()
                if key in digikeyCatalog:
                    digikeyCatalog[key] += results
                else:
                    digikeyCatalog[key] = results
    print("\r", 80*' ', '\rDone')


    #find lowest price break for our quantity
    bomQuantity = args.quantity
    digireelCost = args.digireel_cost if args.digireel_cost is not None else 0
    purchaseOrder = {}
    bReelsOnly = args.reels

    for key, value in bomList.items():
        lineItem = []
        if key in digikeyCatalog:
            catalog = digikeyCatalog[key]
            if catalog is not None:
                purchaseQty = bomQuantity * int(value['Quantity'])
                bestPrice = None
                bestQty = None
                bestChoice = None
                for item in catalog:
                    if not bReelsOnly or (item['packaging'] is not None and
                                          (item['packaging'].startswith('Digi-Reel') or
                                          item['packaging'].startswith('Tape & Reel'))):
                        if purchaseQty <= item['qtyAvailable']:
                            if 'pricing' in item:
                                for qty, price, ext in item['pricing']:
                                    qty = int(qty)
                                    offset = digireelCost if item['packaging'].startswith('Digi-Reel') else 0
                                    if bestPrice is None:
                                        bestPrice = price
                                        bestQty = max(qty, purchaseQty)
                                        bestChoice = item
                                        bestOffset = offset
                                    if purchaseQty >= qty and price * purchaseQty + offset < bestPrice * bestQty + bestOffset:
                                        bestPrice = price
                                        bestQty = purchaseQty
                                        bestChoice = item
                                        bestOffset = offset
                                    elif purchaseQty < qty and qty * price + offset < bestPrice * bestQty + bestOffset:
                                        bestPrice = price
                                        bestQty = qty
                                        bestChoice = item
                                        bestOffset = offset
                            else:
                                print('No pricing info for ', item)
                lineItem = (bestChoice, bestQty, bestPrice)
            else:
                lineItem = ('unknown', 0, 0)
        purchaseOrder[key] = lineItem

    #Write purchase order
    with open(args.output, 'w') as csvfile:
        fieldnames = ['Part Number', 'DK PN', 'vendor', 'mfgPartNumber', 'Qty', 'Unit Price']
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        for key in sorted(purchaseOrder):
            value = purchaseOrder[key]
            if value is not None and len(value) >= 3 and value[0] is not None:
                writer.writerow({'Part Number':key, 'DK PN':value[0]['dkPartNumber'], 'vendor':value[0]['vendor'], 'mfgPartNumber':value[0]['mfgPartNumber'], 'Qty':value[1], 'Unit Price':value[2]})
            else:
                writer.writerow({'Part Number':key, 'vendor':'missing'})

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Generate digikey purchase order from BOM and Parts List')
    parser.add_argument('--bom', action="store", dest="input", help="path to input bom")
    parser.add_argument('--out', action="store", dest="output", help="path to output bom")
    parser.add_argument('--partlist', action="store", dest="list", help="path to parts list")
    parser.add_argument('--url', action="store", dest="digikey_url", help="digikey.com, digikey.ca, etc...")
    parser.add_argument('--qty', action="store", dest="quantity", type=int, help="quantity to buy for")
    parser.add_argument('--reels', action="store_true", help="Add digi-reel or tape & reel only")
    parser.add_argument('--digireel_cost', action="store", dest="digireel_cost", type=float, help="value added cost for digireels")

    main(parser.parse_args())
