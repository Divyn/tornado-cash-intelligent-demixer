"""
Data fetching utilities for Tornado Cash analysis (Bitquery GraphQL)
"""

import json
from decimal import Decimal, InvalidOperation
from dataclasses import dataclass
from typing import List, Dict, Optional, Tuple
from datetime import datetime, timedelta

import requests
import config


@dataclass
class TornadoTransaction:
    """Represents a Tornado Cash transaction"""
    tx_hash: str
    from_address: str
    to_address: str
    value: str
    block_time: str
    gas: int
    call_signature: str
    transaction_type: str  # 'deposit' or 'withdraw'
    # Event-specific fields (from Deposit/Withdrawal events)
    commitment: str = None  # bytes32 from Deposit event
    nullifier: str = None  # bytes32 from Withdrawal event
    recipient: str = None  # address from Withdrawal event
    relayer: str = None  # address from Withdrawal event
    fee: str = None  # uint256 from Withdrawal event


class BitqueryFetcher:
    """Handles Bitquery GraphQL calls for Tornado Cash data"""

    def __init__(self, oauth_token: str, api_url: str = "https://streaming.bitquery.io/graphql"):
        self.oauth_token = oauth_token
        self.api_url = api_url
        self.headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {oauth_token}",
        }

    def _get_date_range(self, start_date: Optional[str], end_date: Optional[str]) -> Tuple[str, str]:
        """
        Build a since/till date tuple with sensible defaults.
        """
        today = datetime.now().strftime("%Y-%m-%d")
        since = start_date or (datetime.now() - timedelta(days=10)).strftime("%Y-%m-%d")
        till = end_date or today
        return since, till

    def _make_query(self, query: str, variables: dict = None) -> Dict:
        payload = {
            "query": query,
            "variables": variables or {},
        }

        try:
            response = requests.post(
                self.api_url,
                headers=self.headers,
                data=json.dumps(payload),
                timeout=90,
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"Error making API request: {e}")
            return {"data": None, "errors": [str(e)]}

    def get_deposits_and_withdrawals_via_transfers(
        self,
        contract_addresses: List[str],
        limit: int = 1000,
        network: str = "eth",
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> List[TornadoTransaction]:
        """
        Retrieve deposits and withdrawals using Transfers query
        This captures transactions going through the Router contract and detects
        the actual pool transfers using Log signatures (Deposit/Withdrawal events)
        """
        # Use provided addresses or get from config for the network
        if not contract_addresses:
            contract_addresses = config.get_tornado_cash_addresses(network)
        addresses_str = json.dumps(contract_addresses)
        since, till = self._get_date_range(start_date, end_date)

        query = f"""
        query MyQuery {{
          EVM(dataset: archive, network: {network}) {{
            Transfers(
              where: {{
                Transaction: {{
                  To: {{in: {addresses_str}}}
                }},
                Block: {{
                  Date: {{
                    since: "{start_date}", till: "{end_date}"
                  }}
                }}
              }}
              orderBy: {{descending: Block_Number}}
              limit: {{count: {limit}}}
            ) {{
              Transaction {{
                Hash
                From
                To
                Gas
                Value
              }}
              Transfer {{
                Amount
                Sender
                Receiver
                Currency {{
                  Symbol
                  Name
                }}
                AmountInUSD
                Index
              }}
              Block {{
                Time
                Number
              }}
              Log {{
                Signature {{
                  Name
                }}
                SmartContract
              }}
            }}
          }}
        }}
        """

        result = self._make_query(query)
        transactions: List[TornadoTransaction] = []

        if not result or result.get("data") is None:
            if result and result.get("errors"):
                print(f"Bitquery returned errors for transfers: {result['errors']}")
            else:
                print("No transfer data returned from Bitquery (API error or timeout).")
            if result:
                print(f"Full result keys: {result.keys()}")
                if result.get("errors"):
                    print(f"Errors: {result['errors']}")
            return transactions
        
        evm_data = result.get("data", {}).get("EVM") or []
        if not evm_data:
            if result.get("errors"):
                print(f"Bitquery returned errors for transfers: {result['errors']}")
            else:
                print("No transfer data returned from Bitquery (empty EVM array).")
                print(f"Result keys: {result.keys() if result else 'None'}")
            return transactions

        evm_entry = evm_data[0] if isinstance(evm_data, list) else evm_data
        if not isinstance(evm_entry, dict):
            print(f"Unexpected EVM format for transfers: {type(evm_entry)}")
            return transactions

        transfers = evm_entry.get("Transfers", []) or []
        

        # Normalize contract addresses to lowercase for comparison
        contract_addresses_lower = {addr.lower() for addr in contract_addresses}
        router_address = "0xd90e2f925da726b50c4ed8d0fb90ad053324f31b".lower()
        
        for transfer_data in transfers:
            tx_data = transfer_data.get("Transaction", {})
            block_data = transfer_data.get("Block", {})
            transfer_info = transfer_data.get("Transfer", {})
            log_data = transfer_data.get("Log", {}) or {}
            
            # Get transfer details
            sender = transfer_info.get("Sender", "").lower()
            receiver = transfer_info.get("Receiver", "").lower()
            
            # Infer transaction type from transfer direction
            # Deposit: User -> Pool (receiver is pool) OR Router -> Pool
            # Withdrawal: Pool -> User (sender is pool) OR Pool -> Router -> User
            is_deposit = False
            is_withdrawal = False
            event_name = ""
            
            if receiver in contract_addresses_lower:
                # Receiver is a pool address = Deposit (user/router sending to pool)
                is_deposit = True
                event_name = "Deposit"
            elif sender in contract_addresses_lower:
                # Sender is a pool address = Withdrawal (pool sending to user/router)
                is_withdrawal = True
                event_name = "Withdrawal"
            else:
                # Neither sender nor receiver is a known pool, skip
                continue
            
            # Get the pool contract address and set from/to addresses
            # For deposits: receiver is pool (user/router -> pool)
            # For withdrawals: sender is pool (pool -> user/router)
            if is_deposit:
                pool_address = receiver  # Deposit: receiver is the pool
                # from_addr is the user (or original sender if going through router)
                from_addr = sender if sender not in contract_addresses_lower else tx_data.get("From", "")
                to_addr = pool_address
                recipient = None
            else:
                pool_address = sender  # Withdrawal: sender is the pool
                from_addr = pool_address
                # to_addr is the recipient (user or router)
                to_addr = receiver
                # recipient is the final user (not router or pool)
                recipient = receiver if receiver not in contract_addresses_lower and receiver != router_address else None
            
            # Get transfer amount
            transfer_amount = transfer_info.get("Amount", 0)
            currency = transfer_info.get("Currency", {})
            currency_symbol = currency.get("Symbol", "ETH")
            
            # Convert amount to ETH string
            if transfer_amount:
                # Amount is typically in wei for ETH
                if currency_symbol == "ETH" or currency_symbol == "":
                    try:
                        value_str = str(Decimal(str(transfer_amount)) / Decimal("1e18"))
                    except (InvalidOperation, ValueError, TypeError):
                        value_str = "0"
                else:
                    # For other tokens, keep as is (would need token decimals)
                    value_str = str(transfer_amount)
            else:
                # Fallback to transaction value
                tx_value = tx_data.get("Value", 0)
                try:
                    value_str = str(Decimal(str(tx_value)) / Decimal("1e18"))
                except (InvalidOperation, ValueError, TypeError):
                    value_str = "0"
            
            transaction_type = "deposit" if is_deposit else "withdraw"
            
            # Note: Transfers query doesn't provide event arguments (commitments, nullifiers, relayers, fees)
            # These would need to be fetched separately via Events query if needed
            commitment = None
            nullifier = None
            relayer = None
            fee = None
            
            transactions.append(
                TornadoTransaction(
                    tx_hash=tx_data.get("Hash", ""),
                    from_address=from_addr,
                    to_address=to_addr,
                    value=value_str,
                    block_time=block_data.get("Time", ""),
                    gas=tx_data.get("Gas", 0),
                    call_signature=event_name,
                    transaction_type=transaction_type,
                    commitment=commitment,
                    nullifier=nullifier,
                    recipient=recipient,
                    relayer=relayer,
                    fee=fee,
                )
            )

        return transactions

    def get_deposit_and_withdrawal_events(
        self,
        contract_addresses: List[str],
        limit: int = 1000,
        network: str = "eth",
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> List[TornadoTransaction]:
        """
        Retrieve both Deposit and Withdrawal events in a single API call
        """
        # Use provided addresses or get from config for the network
        if not contract_addresses:
            contract_addresses = config.get_tornado_cash_addresses(network)
        addresses_str = json.dumps(contract_addresses)
        since, till = self._get_date_range(start_date, end_date)

        query = f"""
        query MyQuery {{
          EVM(dataset: archive, network: {network}) {{
            Events(
              where: {{
                Log: {{
                  SmartContract: {{in: {addresses_str}}},
                  Signature: {{
                    Name: {{in: ["Deposit", "Withdrawal"]}}
                  }}
                }},
                Block: {{
                  Date: {{
                    since: "{start_date}", till: "{end_date}"
                  }}
                }}
              }}
              orderBy: {{descending: Block_Number}}
              limit: {{count: {limit}}}
            ) {{
              Log {{
                SmartContract
                Signature {{
                  Name
                }}
              }}
              Transaction {{
                From
                To
                Hash
                Value
                Gas
                Type
              }}
              Block {{
                Time
                Date
              }}
              Arguments {{
                Value {{
                  ... on EVM_ABI_Bytes_Value_Arg {{
                    hex
                  }}
                  ... on EVM_ABI_Integer_Value_Arg {{
                    integer
                  }}
                  ... on EVM_ABI_Address_Value_Arg {{
                    address
                  }}
                  ... on EVM_ABI_BigInt_Value_Arg {{
                    bigInteger
                  }}
                  ... on EVM_ABI_String_Value_Arg {{
                    string
                  }}
                  ... on EVM_ABI_Boolean_Value_Arg {{
                    bool
                  }}
                }}
                Name
              }}
            }}
          }}
        }}
        """

        result = self._make_query(query)
   
        transactions: List[TornadoTransaction] = []

        if not result or result.get("data") is None:
            if result and result.get("errors"):
                print(f"Bitquery returned errors for deposit/withdrawal events: {result['errors']}")
            else:
                print("No deposit/withdrawal event data returned from Bitquery (API error or timeout).")
            return transactions
        
        evm_data = result.get("data", {}).get("EVM") or []
        if not evm_data:
            if result.get("errors"):
                print(f"Bitquery returned errors for deposit/withdrawal events: {result['errors']}")
            else:
                print("No deposit/withdrawal event data returned from Bitquery (empty EVM array).")
            return transactions

        evm_entry = evm_data[0] if isinstance(evm_data, list) else evm_data
        if not isinstance(evm_entry, dict):
            print(f"Unexpected EVM format for deposit/withdrawal events: {type(evm_entry)}")
            return transactions

        events = evm_entry.get("Events", []) or []

        for event_data in events:
            tx_data = event_data.get("Transaction", {})
            block_data = event_data.get("Block", {})
            log_data = event_data.get("Log", {})
            arguments = event_data.get("Arguments", []) or []

            # Determine event type
            event_name = log_data.get("Signature", {}).get("Name", "")
            is_deposit = event_name == "Deposit"
            is_withdrawal = event_name == "Withdrawal"

            # Extract event-specific arguments
            commitment = None
            nullifier = None
            recipient = None
            relayer = None
            fee = None

            for arg in arguments:
                arg_name = arg.get("Name", "").lower()
                value_obj = arg.get("Value", {})

                if is_deposit and (arg_name == "commitment"):
                    if "hex" in value_obj:
                        commitment = value_obj["hex"]
                elif is_withdrawal:
                    if arg_name == "nullifierhash" or arg_name == "nullifier":
                        if "hex" in value_obj:
                            nullifier = value_obj["hex"]
                    elif arg_name == "to" or arg_name == "recipient":
                        if "address" in value_obj:
                            recipient = value_obj["address"]
                    elif arg_name == "relayer":
                        if "address" in value_obj:
                            relayer = value_obj["address"]
                    elif arg_name == "fee":
                        if "bigInteger" in value_obj:
                            fee = str(value_obj["bigInteger"])
                        elif "integer" in value_obj:
                            fee = str(value_obj["integer"])

            # Convert transaction value from wei to ETH
            tx_value = tx_data.get("Value", 0)
            try:
                value_str = str(Decimal(str(tx_value)) / Decimal("1e18"))
            except (InvalidOperation, ValueError, TypeError):
                value_str = "0"

            transaction_type = "deposit" if is_deposit else "withdraw"

            transactions.append(
                TornadoTransaction(
                    tx_hash=tx_data.get("Hash", ""),
                    from_address=tx_data.get("From", ""),
                    to_address=tx_data.get("To", ""),
                    value=value_str,
                    block_time=block_data.get("Time", ""),
                    gas=tx_data.get("Gas", 0),
                    call_signature=event_name,
                    transaction_type=transaction_type,
                    commitment=commitment,
                    nullifier=nullifier,
                    recipient=recipient,
                    relayer=relayer,
                    fee=fee,
                )
            )

        return transactions

    def get_withdrawal_events(
        self,
        contract_addresses: List[str],
        limit: int = 1000,
        network: str = "eth",
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> List[TornadoTransaction]:
        """
        Retrieve only Withdrawal events
        This is a convenience method that filters get_deposit_and_withdrawal_events
        """
        all_events = self.get_deposit_and_withdrawal_events(
            contract_addresses, limit, network, start_date, end_date
        )
        return [tx for tx in all_events if tx.transaction_type == "withdraw"]

    