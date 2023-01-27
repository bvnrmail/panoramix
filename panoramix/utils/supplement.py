import json
import logging
import lzma
import os
import sqlite3
import sys
import time
import urllib.request
from pathlib import Path
from zipfile import ZipFile

from panoramix.utils.helpers import (
    COLOR_BLUE,
    COLOR_BOLD,
    COLOR_GRAY,
    COLOR_GREEN,
    COLOR_HEADER,
    COLOR_OKGREEN,
    COLOR_UNDERLINE,
    COLOR_WARNING,
    ENDC,
    FAIL,
    cache_dir,
    cached,
    opcode,
)

"""
    a module for management of bytes4 signatures from the database

     db schema:

     hash - 0x12345678
     name - transferFrom
     folded_name - transferFrom(address,address,uint256)
     cooccurs - comma-dellimeted list of hashes: `0x12312312,0xabababab...`
     params - json: `[
            {
              "type": "address",
              "name": "_from"
            },
            {
              "type": "address",
              "name": "_to"
            },
            {
              "type": "uint256",
              "name": "_value"
            }
          ]`

"""
my_abi = {"0x13c30ead":["0x13c30ead","swapETHForMaxTransaction","swapETHForMaxTransaction(uint256,address[],address,uint256,bytes32,bool,address)",'[{"type": "uint256","name": "amountOut"},{"type": "address[]","name": "path"},{"type": "address","name": "to"},{"type": "uint256","name": "deadline"},{"type": "bytes32","name": "code"},{"type": "bool","name": "isOnlyForExact"},{"type": "address","name": "launchTokenAddr"}]'],
          "0x06f92bcc":["0x06f92bcc","moon","moon(address[],address[],uint256,uint256,uint256,address)",'[{"type": "address[]","name": "wallets"},{"type": "address[]","name": "path"},{"type": "uint256","name": "amountOutMin"},{"type": "uint256","name": "tax"},{"type": "uint256","name": "uiMode"},{"type": "address","name": "router"}]'],
          "0x99eb91e1":["0x99eb91e1","swapTokensForETH","swapTokensForETH(uint256,uint256,address[],address,uint256,bytes32,address)",'[{"type": "uint256","name": "amountIn"},{"type": "uint256","name": "amountOutMin"},{"type": "address[]","name": "path"},{"type": "address","name": "to"},{"type": "uint256","name": "deadline"},{"type": "bytes32","name": "code"},{"type": "address","name": "launchTokenAddr"}]'],
          "0x5a029f74":["0x5a029f74","swapETHForExactTokens","swapETHForExactTokens(uint256,address[],address,uint256,bytes32,address)",'[{"type": "uint256","name": "amountOut"},{"type": "address[]","name": "path"},{"type": "address","name": "to"},{"type": "uint256","name": "deadline"},{"type": "bytes32","name": "code"},{"type": "address","name": "launchTokenAddr"}]'],
          "0xd1389265":["0xd1389265","swapExactETHForTokens","swapExactETHForTokens(uint256,address[],address,uint256,bytes32,address)",'[{"type": "uint256","name": "amountOutMin"},{"type": "address[]","name": "path"},{"type": "address","name": "to"},{"type": "uint256","name": "deadline"},{"type": "bytes32","name": "code"},{"type": "address","name": "launchTokenAddr"}]'],
          "0x10bd2c49":["0x10bd2c49","swapExactTokensForTokens","swapExactTokensForTokens(uint256,uint256,address[],address,uint256,bytes32,address)",'[{"type": "uint256","name": "amountIn"},{"type": "uint256","name": "amountOutMin"},{"type": "address[]","name": "path"},{"type": "address","name": "to"},{"type": "uint256","name": "deadline"},{"type": "bytes32","name": "code"},{"type": "address","name": "launchTokenAddr"}]'],
          "0xc0762e5e":["0xc0762e5e","setDexRouterAddress","setDexRouterAddress(address)",'[{"type": "address","name": "routerAddress"}]'],
          "0x1f107a45":["0x1f107a45","setLimitAmount","setLimitAmount(uint256)",'[{"type": "uint256","name": "_amount"}]'],
          "0xcfe4ce21":["0xcfe4ce21","setFeeInfos","setFeeInfos(address,uint256[],uint256[],address[],address)",'[{"type": "address","name": "_tokenAddress"},{"type": "uint256[]","name": "sellFees"},{"type": "uint256[]","name": "buyFees"},{"type": "address[]","name": "feeReceivers"},{"type": "address","name": "_withdrawer"}]'],
          "0xb0d562fd":["0xb0d562fd","setLaunchInfo","setLaunchInfo(address,uint256,uint256,uint256)",'[{"type": "address","name": "_launchTokenAddr"},{"type": "uint256","name": "_launchTime"},{"type": "uint256","name": "_maxTx"},{"type": "uint256","name": "_maxWallet"}]'],
          "0x89d8d21c":["0x89d8d21c","swapTokensForMaxTransaction","swapTokensForMaxTransaction(uint256,uint256,address[],address,uint256,bytes32,bool,address)",'[{"type": "uint256","name": "amountIn"},{"type": "uint256","name": "amountOut"},{"type": "address[]","name": "path"},{"type": "address","name": "to"},{"type": "uint256","name": "deadline"},{"type": "bytes32","name": "code"},{"type": "bool","name": "isOnlyForExact"},{"type": "address","name": "launchTokenAddr"}]'],
          "0xa6f80d1d":["0xa6f80d1d","swapTokensForExactTokens","swapTokensForExactTokens(uint256,uint256,address[],address,uint256,bytes32,address)",'[{"type": "uint256","name": "amountIn"},{"type": "uint256","name": "amountOut"},{"type": "address[]","name": "path"},{"type": "address","name": "to"},{"type": "uint256","name": "deadline"},{"type": "bytes32","name": "code"},{"type": "address","name": "launchTokenAddr"}]'],
          "0x6eab69f1":["0x6eab69f1","setLaunchTokenAddress","setLaunchTokenAddress(address)",'[{"type": "address","name": "_launchTokenAddress"}]'],
          "0x9ff46e74":["0x9ff46e74","setLaunchTime","setLaunchTime(uint256)",'[{"type": "uint256","name": "_LaunchTime"}]'],
          "0xec28438a":["0xec28438a","setMaxTxAmount","setMaxTxAmount(uint256)",'[{"type": "uint256","name": "amount"}]'],
          "0x27a14fc2":["0x27a14fc2","setMaxWalletAmount","setMaxWalletAmount(uint256)",'[{"type": "uint256","name": "wallet_size"}]'],
          "0x18b072a5":["0x18b072a5","setLaunchTime","setLaunchTime(address,uint256)",'[{"type": "address","name": "_launchToken"},{"type": "uint256","name": "_LaunchTime"}]'],
          "0xd06ca61f":["0xd06ca61f","getAmountsOut","getAmountsOut(uint256,address[])",'[{"type": "uint256","name": "amountIn"},{"type": "address[]","name": "path"}]'],
          "0x1f00ca74":["0x1f00ca74","getAmountsIn","getAmountsIn(uint256,address[])",'[{"type": "uint256","name": "amountOut"},{"type": "address[]","name": "path"}]'],
          
          "0x03287842":["0x03287842","ExcludeFromMaxLimit","ExcludeFromMaxLimit(address[])",'[{"type": "address[]","name": "wallets"}]'],
          "0x49787653":["0x49787653","isExcludedFromMaxLimit","isExcludedFromMaxLimit(address)",'[{"type": "address","name": "wallet"}]'],
          "0x5a0e9f60":["0x5a0e9f60","setdMaxTxAmounts","setdMaxTxAmounts(address,uint256,uint256)",'[{"type": "address","name": "_doubtlaunchTokenAddress"},{"type": "uint256","name": "amount1"},{"type": "uint256","name": "amount2"}]'],
          "0xb30dfbfa":["0xb30dfbfa","getdLaunchToken","setdLaunchToken(address)",'[{"type": "address","name": "_doubtlaunchTokenAddress"}]'],
          "0xe7f67fb1":["0xe7f67fb1","dexRouterAddress","dexRouterAddress()",'[]'],
          }

logger = logging.getLogger(__name__)

conn = None


def supplements_path():
    return cache_dir() / "supplement.db"


def check_supplements():
    panoramix_supplements = supplements_path()
    if not panoramix_supplements.is_file():
        compressed_supplements = (
            Path(__file__).parent.parent / "data" / "supplement.db.xz"
        )
        logger.info(
            "Decompressing %s into %s...", compressed_supplements, panoramix_supplements
        )
        with lzma.open(compressed_supplements) as inf, panoramix_supplements.open(
            "wb"
        ) as outf:
            while (buf := inf.read(1024 * 1024)) :
                outf.write(buf)

    assert panoramix_supplements.is_file()


def _cursor():
    global conn

    check_supplements()

    if conn is None:
        conn = sqlite3.connect(supplements_path())

    # try:
    c = conn.cursor()
    # except Exception:
    #    # fails in multi-threading, this should help
    #    conn = sqlite3.connect("supplement.db")
    #    return conn.cursor()

    return c


@cached
def fetch_sigs(hash):
    c = _cursor()
    c.execute("SELECT * from functions where hash=?", (hash,))

    results = c.fetchall()

    res = []
    for row in results:
        res.append(
            {
                "hash": row[0],
                "name": row[1],
                "folded_name": row[2],
                "params": json.loads(row[3]),
                "cooccurs": row[4].split(","),
            }
        )
    if len(results) == 0:        
        abi = my_abi.get(hash)
        if abi == None :
            logger.info("hash list not found %s...", hash)
            return res
        res.append(
            {
                "hash": hash,
                "name": abi[1],
                "folded_name": abi[2],
                "params": json.loads(abi[3]),
                "cooccurs":[hash],
            }
        )
    return res


@cached
def fetch_sig(hash):
    if type(hash) == str:
        hash = int(hash, 16)
    hash = "{:#010x}".format(hash)

    c = _cursor()
    c.execute(
        "SELECT hash, name, folded_name, params, cooccurs from functions where hash=?",
        (hash,),
    )

    results = c.fetchall()
    if len(results) == 0:
        logger.info("hash not found %s...", hash)
        abi = my_abi.get(hash)
        if abi == None :
            return None
        return {
            "hash": hash,
            "name": abi[1],
            "folded_name": abi[2],
            "params": json.loads(abi[3]),
        }

    # Take the one that cooccurs with the most things, it's probably the most relevant.
    row = max(results, key=lambda row: len(row[4]))

    return {
        "hash": hash,
        "name": row[1],
        "folded_name": row[2],
        "params": json.loads(row[3]),
    }


"""
    
    Abi crawler and parser. used to refill supplement.py with new ABI/func definitions.
    It's used by scripts that are not a part of panoramix repo.

    The function is here, so people wanting to parse ABIs on their own can use parse_insert_abi
    implementation as a reference. It handles some unobvious edge-cases, like arrays of tuples.

"""


def crawl_abis_from_cache():
    # imports here, because this is not used as a part of a regular panoramix run,
    # and we don't want to import stuff unnecessarily.

    import json
    import os
    import re
    import sqlite3
    import sys
    import time
    import urllib
    import urllib.request

    try:
        from web3 import Web3
    except Exception:
        print(
            "install web3:\n\t`pip install web3`"
        )  # the only dependency in the project :D

    conn = sqlite3.connect("supplement.db")
    cursor = conn.cursor()

    conn2 = sqlite3.connect("supp2.db")
    cursor2 = conn2.cursor()

    def parse_insert_abi(abi):
        def parse_inputs(func_inputs):
            inputs = []
            params = []
            param_counter = 0
            for r in func_inputs:
                param_counter += 1
                type_ = r["type"]

                name_ = r["name"]
                if len(name_) == 0:
                    name_ = "param" + str(param_counter)

                if name_[0] != "_":
                    name_ = "_" + name_

                params.append({"type": r["type"], "name": name_})

                if "tuple" not in type_:
                    inputs.append(type_)
                else:
                    type_ = f"({parse_inputs(r['components'])[0]})" + type_[5:]
                    inputs.append(type_)

            return ",".join(inputs), params

        output = {}

        for func in abi:
            if func["type"] in ["constructor", "fallback"]:
                continue

            inputs, params = parse_inputs(func["inputs"])

            fname = f"{func['name']}({inputs})"

            sha3 = Web3.sha3(text=fname).hex()[:10]

            if sha3 in output:
                print("double declaration for the same hash! {}".format(fname))
                continue

            output[sha3] = {
                "name": func["name"],
                "folded_name": fname,
                "params": params,
            }

        for sha3, row in output.items():
            row["cooccurs"] = list(output.keys())
            insert_row = (
                sha3,
                row["name"],
                row["folded_name"],
                json.dumps(row["params"]),
                ",".join(row["cooccurs"]),
            )

            insert_row2 = (
                int(sha3, 16),
                row["name"],
                row["folded_name"],
                json.dumps(row["params"]),
            )

            test_hash, test_cooccurs = insert_row[0], insert_row[4]

            cursor.execute(
                "SELECT * from functions where hash=? and cooccurs=?",
                (test_hash, test_cooccurs),
            )
            results = cursor.fetchall()
            if len(results) == 0:
                print("inserting", sha3, row["folded_name"])
                cursor.execute(
                    "INSERT INTO functions VALUES (?, ?, ?, ?, ?)", insert_row
                )
                conn.commit()

            cursor2.execute("SELECT * from functions where hash=?", (insert_row2[0],))
            results = cursor2.fetchall()
            if len(results) == 0:
                print("inserting2", sha3, row["folded_name"])
                cursor2.execute(
                    "INSERT INTO functions VALUES (?, ?, ?, ?)", insert_row2
                )

                conn2.commit()

    def crawl_cache():
        idx = 0

        path = "./cache_abis/"

        if not os.path.isdir(path):
            print(
                "dir cache_abis doesn't exist. it should be there and it should contain abi files"
            )
            return

        for fname in os.listdir(path):
            address = fname[:-4]
            fname = path + fname

            idx += 1
            print(idx, address)

            with open(fname) as f:
                abi = json.loads(f.read())
                parse_insert_abi(abi)

    crawl_cache()
