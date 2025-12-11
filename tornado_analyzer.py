"""
Tornado Cash Analyzer - Track and analyze Tornado Cash transactions
"""

import json
from datetime import datetime
from typing import List, Dict, Optional
from collections import defaultdict, Counter

from afetch import TornadoTransaction, BitqueryFetcher
import config
from scoring import calculate_match_score, check_amount_match


class TornadoCashAnalyzer:
    """Main class for analyzing Tornado Cash transactions"""
    
    # OFAC-Sanctioned Tornado Cash contract addresses
    # Source: U.S. Treasury OFAC SDN List - August 8, 2022
    TORNADO_CONTRACTS = [
        "0x8589427373D6D84E98730D7795D8f6f8731FDA16",
        "0x722122dF12D4e14e13Ac3b6895a86e84145b6967",
        "0xDD4c48C0B24039969fC16D1cdF626eaB821d3384",
        "0xd90e2f925DA726b50C4Ed8D0Fb90Ad053324F31b",
        "0xd96f2B1c14Db8458374d9Aca76E26c3D18364307",
        "0x4736dCf1b7A3d580672CcE6E7c65cd5cc9cFBa9D",
        "0xD4B88Df4D29F5CedD6857912842cff3b20C8Cfa3",
        "0x910Cbd523D972eb0a6f4cAe4618aD62622b39DbF",
        "0xA160cdAB225685dA1d56aa342Ad8841c3b53f291",
        "0xFD8610d20aA15b7B2E3Be39B396a1bC3516c7144",
        "0xF60dD140cFf0706bAE9Cd734Ac3ae76AD9eBC32A",
        "0x22aaA7720ddd5388A3c0A3333430953C68f1849b",
        "0xBA214C1c1928a32Bffe790263E38B4Af9bFCD659",
        "0xb1C8094B234DcE6e03f10a5b673c1d8C69739A00",
        "0x527653eA119F3E6a1F5BD18fbF4714081D7B31ce",
        "0x58E8dCC13BE9780fC42E8723D8EaD4CF46943dF2",
        "0xD691F27f38B395864Ea86CfC7253969B409c362d",
        "0xaEaaC358560e11f52454D997AAFF2c5731B6f8a6",
        "0x1356c899D8C9467C7f71C195612F8A395aBf2f0a",
        "0xA60C772958a3eD56c1F15dD055bA37AC8e523a0D",
        "0x169AD27A470D064DEDE56a2D3ff727986b15D52B",
        "0x0836222F2B2B24A3F36f98668Ed8F0B38D1a872f",
        "0xF67721A2D8F736E75a49FdD7FAd2e31D8676542a",
        "0x9AD122c22B14202B4490eDAf288FDb3C7cb3ff5E",
        "0x905b63Fff465B9fFBF41DeA908CEb12478ec7601",
        "0x07687e702b410Fa43f4cB4Af7FA097918ffD2730",
        "0x94A1B5CdB22c43faab4AbEb5c74999895464Ddaf",
        "0xb541fc07bC7619fD4062A54d96268525cBC6FfEF",
        "0x12D66f87A04A9E220743712cE6d9bB1B5616B8Fc",
        "0x47CE0C6eD5B0Ce3d3A51fdb1C52DC66a7c3c2936",
        "0x23773E65ed146A459791799d01336DB287f25334",
        "0xD21be7248e0197Ee08E0c20D4a96DEBdaC3D20Af",
        "0x610B717796ad172B316836AC95a2ffad065CeaB4",
        "0x178169B423a011fff22B9e3F3abeA13414dDD0F1",
        "0xbB93e510BbCD0B7beb5A853875f9eC60275CF498",
        "0x2717c5e28cf931547B621a5dddb772Ab6A35B701",
        "0x03893a7c7463AE47D46bc7f091665f1893656003",
        "0xCa0840578f57fE71599D29375e16783424023357",
    ]
    
    def __init__(self, oauth_token: str, api_url: str = "https://streaming.bitquery.io/graphql", fetcher: BitqueryFetcher = None, network: str = "eth"):
        """
        Initialize the analyzer
        
        Args:
            oauth_token: Bitquery OAuth token
            api_url: Bitquery API endpoint
            fetcher: Optional custom fetcher for dependency injection
            network: Network identifier (eth, matic, bsc, etc.)
        """
        self.fetcher = fetcher or BitqueryFetcher(oauth_token=oauth_token, api_url=api_url)
        self.network = network
        self.deposits: List[TornadoTransaction] = []
        self.withdrawals: List[TornadoTransaction] = []
    
    def get_deposits(
        self,
        contract_addresses: List[str],
        limit: int = 1000,
        network: str = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> List[TornadoTransaction]:
        """
        Retrieve deposit transactions to Tornado Cash contracts
        Uses transfers query to capture deposits
        
        Args:
            contract_addresses: List of contract addresses to query
            limit: Maximum number of transactions to retrieve
            network: Network identifier (eth, matic, bsc, etc.). Uses instance network if not provided.
        """
        if network is None:
            network = self.network
        all_transactions = self.fetcher.get_deposits_and_withdrawals_via_transfers(
            contract_addresses,
            limit,
            network,
            start_date,
            end_date,
        )
        transactions = [tx for tx in all_transactions if tx.transaction_type == "deposit"]
        self.deposits.extend(transactions)
        return transactions
    
    def get_withdrawals(
        self,
        contract_addresses: List[str],
        limit: int = 1000,
        network: str = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> List[TornadoTransaction]:
        """
        Retrieve withdrawal transactions from Tornado Cash contracts
        Uses transfers query to capture withdrawals
        
        Args:
            contract_addresses: List of contract addresses to query
            limit: Maximum number of transactions to retrieve
            network: Network identifier (eth, matic, bsc, etc.). Uses instance network if not provided.
        """
        if network is None:
            network = self.network
        all_transactions = self.fetcher.get_deposits_and_withdrawals_via_transfers(
            contract_addresses,
            limit,
            network,
            start_date,
            end_date,
        )
        transactions = [tx for tx in all_transactions if tx.transaction_type == "withdraw"]
        self.withdrawals.extend(transactions)
        return transactions
    
    def get_deposit_and_withdrawal_events(
        self,
        contract_addresses: List[str],
        limit: int = 1000,
        network: str = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> List[TornadoTransaction]:
        """
        Retrieve deposits and withdrawals directly via event queries.
        NOTE: This should only be used for event-specific analysis (relayers, nullifiers)
        For general deposit/withdrawal tracking, use get_deposits()/get_withdrawals() which use transfers
        
        Args:
            contract_addresses: List of contract addresses to query
            limit: Maximum number of transactions to retrieve
            network: Network identifier (eth, matic, bsc, etc.). Uses instance network if not provided.
        """
        if network is None:
            network = self.network
        
        # Use direct event query for event-specific data (relayers, nullifiers)
        all_events = self.fetcher.get_deposit_and_withdrawal_events(
            contract_addresses,
            limit,
            network,
            start_date,
            end_date,
        )
        
        # Don't extend deposits/withdrawals here - events are only for specific analysis
        return all_events
    
    def get_deposit_events(self, contract_addresses: List[str], limit: int = 1000, network: str = None) -> List[TornadoTransaction]:
        """
        Retrieve Deposit events from Tornado Cash contracts
        Captures commitment (bytes32) which is critical for tracking deposits
        NOTE: This should only be used for event-specific analysis (commitments)
        For general deposit tracking, use get_deposits() which uses transfers
        
        Args:
            contract_addresses: List of contract addresses to query
            limit: Maximum number of transactions to retrieve
            network: Network identifier (eth, matic, bsc, etc.). Uses instance network if not provided.
        """
        if network is None:
            network = self.network
        transactions = self.fetcher.get_deposit_events(contract_addresses, limit, network)
        # Don't extend deposits here - events are only for specific analysis
        return transactions
    
    def get_withdrawal_events(self, contract_addresses: List[str], limit: int = 1000, network: str = None, start_date: Optional[str] = None, end_date: Optional[str] = None) -> List[TornadoTransaction]:
        """
        Retrieve Withdrawal events from Tornado Cash contracts
        Captures nullifier, recipient, relayer, and fee which are critical for analysis
        NOTE: This should only be used for event-specific analysis (nullifiers, relayers)
        For general withdrawal tracking, use get_withdrawals() which uses transfers
        
        Args:
            contract_addresses: List of contract addresses to query
            limit: Maximum number of transactions to retrieve
            network: Network identifier (eth, matic, bsc, etc.). Uses instance network if not provided.
            start_date: Optional start date for filtering (YYYY-MM-DD)
            end_date: Optional end date for filtering (YYYY-MM-DD)
        """
        if network is None:
            network = self.network
        transactions = self.fetcher.get_withdrawal_events(contract_addresses, limit, network, start_date, end_date)
        # Don't extend withdrawals here - events are only for specific analysis
        return transactions
    
    def analyze_timestamps(self, transactions: List[TornadoTransaction]) -> Dict:
        """
        Analyze transaction timestamps for patterns
        
        Args:
            transactions: List of transactions to analyze
            
        Returns:
            Dictionary with timestamp analysis results
        """
        if not transactions:
            return {}
        
        timestamps = []
        for tx in transactions:
            try:
                ts = datetime.fromisoformat(tx.block_time.replace('Z', '+00:00'))
                timestamps.append(ts)
            except:
                continue
        
        if not timestamps:
            return {}
        
        # Daily activity
        daily_counts = Counter()
        hourly_counts = Counter()
        
        for ts in timestamps:
            day_key = ts.strftime('%Y-%m-%d')
            hour_key = f"{day_key} {ts.hour:02d}:00"
            daily_counts[day_key] += 1
            hourly_counts[hour_key] += 1
        
        # Find clusters
        most_active_day = daily_counts.most_common(1)[0] if daily_counts else None
        most_active_hour = hourly_counts.most_common(1)[0] if hourly_counts else None
        
        return {
            "total_transactions": len(transactions),
            "daily_activity": dict(daily_counts),
            "hourly_activity": dict(hourly_counts),
            "most_active_day": most_active_day,
            "most_active_hour": most_active_hour,
            "average_per_day": len(transactions) / max(len(set(daily_counts.keys())), 1)
        }
    
    def find_address_reuse(self, transactions: List[TornadoTransaction]) -> Dict[str, int]:
        """
        Find addresses that appear in multiple transactions
        
        Args:
            transactions: List of transactions to analyze
            
        Returns:
            Dictionary mapping addresses to transaction counts
        """
        address_counts = Counter()
        
        for tx in transactions:
            address_counts[tx.from_address] += 1
            address_counts[tx.to_address] += 1
        
        # Filter to addresses with multiple transactions
        reused = {addr: count for addr, count in address_counts.items() if count > 1}
        
        return dict(sorted(reused.items(), key=lambda x: x[1], reverse=True))
    
    def match_deposits_withdrawals(self, tolerance_seconds: int = 1209600, value_tolerance_percent: float = 0.05) -> List[Dict]:
        """
        Match deposits with withdrawals based on timing, amount, and contract
        
        Args:
            tolerance_seconds: Time window in seconds (default 2 weeks)
            value_tolerance_percent: Percentage tolerance for amount matching (default 5% to account for relayer fees)
            
        Returns:
            List of matched deposit-withdrawal pairs (one-to-one matching)
        """
        matches = []
        matched_deposit_indices = set()
        matched_withdrawal_indices = set()
        
        # Create candidate matches with scores
        candidates = []
        
        for i, deposit in enumerate(self.deposits):
            deposit_time = None
            deposit_value = None
            try:
                deposit_time = datetime.fromisoformat(deposit.block_time.replace('Z', '+00:00'))
                deposit_value = float(deposit.value) if deposit.value else None
            except:
                continue
            
            for j, withdrawal in enumerate(self.withdrawals):
                withdrawal_time = None
                withdrawal_value = None
                try:
                    withdrawal_time = datetime.fromisoformat(withdrawal.block_time.replace('Z', '+00:00'))
                    withdrawal_value = float(withdrawal.value) if withdrawal.value else None
                except:
                    continue
                
                # Withdrawal must come AFTER deposit
                if not (withdrawal_time and deposit_time) or withdrawal_time <= deposit_time:
                    continue
                
                # Check time window
                time_diff = (withdrawal_time - deposit_time).total_seconds()
                if time_diff > tolerance_seconds:
                    continue
                
                # Check amount match (with tolerance for relayer fees)
                amount_match = check_amount_match(deposit_value, withdrawal_value, value_tolerance_percent)
                
                # Prefer matches from same contract (same pool)
                # Withdrawals emit from the pool contract (stored in from_address)
                same_contract = deposit.to_address.lower() == withdrawal.from_address.lower()
                
                # Check if same pool denomination using the pool contract for withdrawals
                deposit_pool = config.get_pool_denomination(deposit.to_address, self.network)
                withdrawal_pool = config.get_pool_denomination(withdrawal.from_address, self.network)
                same_pool = deposit_pool == withdrawal_pool and deposit_pool != "Unknown"
                
                if amount_match or (deposit_value and withdrawal_value and withdrawal_value <= deposit_value * 1.1):
                    # Calculate match score (lower is better)
                    score = calculate_match_score(
                        time_diff_seconds=time_diff,
                        tolerance_seconds=tolerance_seconds,
                        deposit_value=deposit_value,
                        withdrawal_value=withdrawal_value,
                        same_contract=same_contract,
                        same_pool=same_pool,
                    )
                    
                    candidates.append({
                        "deposit_idx": i,
                        "withdrawal_idx": j,
                        "deposit": deposit,
                        "withdrawal": withdrawal,
                        "time_diff_seconds": time_diff,
                        "time_diff_days": time_diff / 86400,
                        "time_diff_hours": time_diff / 3600,
                        "amount_match": amount_match,
                        "same_contract": same_contract,
                        "same_pool": same_pool,
                        "deposit_pool": deposit_pool,
                        "withdrawal_pool": withdrawal_pool,
                        "score": score
                    })
        
        # Sort by score (best matches first)
        candidates.sort(key=lambda x: x["score"])
        
        # Greedy one-to-one matching
        for candidate in candidates:
            if candidate["deposit_idx"] not in matched_deposit_indices and \
               candidate["withdrawal_idx"] not in matched_withdrawal_indices:
                matches.append({
                    "deposit": candidate["deposit"],
                    "withdrawal": candidate["withdrawal"],
                    "time_diff_seconds": candidate["time_diff_seconds"],
                    "time_diff_days": candidate["time_diff_days"],
                    "time_diff_hours": candidate["time_diff_hours"],
                    "amount_match": candidate["amount_match"],
                    "same_contract": candidate["same_contract"],
                    "same_pool": candidate["same_pool"],
                    "deposit_pool": candidate["deposit_pool"],
                    "withdrawal_pool": candidate["withdrawal_pool"]
                })
                matched_deposit_indices.add(candidate["deposit_idx"])
                matched_withdrawal_indices.add(candidate["withdrawal_idx"])
        
        return matches
    
    def analyze_network_patterns(self, time_window_days: int = 14) -> Dict:
        """
        Analyze network patterns by looking at addresses that interacted
        with Tornado Cash within a time window
        
        Args:
            time_window_days: Time window in days to consider
            
        Returns:
            Dictionary with network analysis results
        """
        all_transactions = self.deposits + self.withdrawals
        
        if not all_transactions:
            return {}
        
        # Group transactions by time windows
        time_windows = defaultdict(list)
        
        for tx in all_transactions:
            try:
                tx_time = datetime.fromisoformat(tx.block_time.replace('Z', '+00:00'))
                window_key = tx_time.strftime('%Y-W%W')  # Week-based window
                time_windows[window_key].append(tx)
            except:
                continue
        
        # Find common addresses across windows
        address_sets = {}
        for window, txs in time_windows.items():
            addresses = set()
            for tx in txs:
                addresses.add(tx.from_address)
                addresses.add(tx.to_address)
            address_sets[window] = addresses
        
        # Find intersections
        common_addresses = set()
        if len(address_sets) > 1:
            windows = list(address_sets.values())
            common_addresses = set.intersection(*windows) if windows else set()
        
        return {
            "time_windows": {k: len(v) for k, v in time_windows.items()},
            "common_addresses": list(common_addresses),
            "total_unique_addresses": len(set(
                addr for txs in time_windows.values() 
                for tx in txs 
                for addr in [tx.from_address, tx.to_address]
            ))
        }
    
    def analyze_relayers(self, contract_addresses: List[str] = None, limit: int = 1000, network: str = None, withdrawal_events: List[TornadoTransaction] = None, start_date: Optional[str] = None, end_date: Optional[str] = None) -> Dict:
        """
        Analyze relayer usage patterns from withdrawal events
        NOTE: This requires event data (relayer field is only available in events)
        
        Args:
            contract_addresses: List of contract addresses to query (if not provided, uses instance data)
            limit: Maximum number of transactions to retrieve
            network: Network identifier (eth, matic, bsc, etc.). Uses instance network if not provided.
            withdrawal_events: Pre-fetched withdrawal events to use (avoids duplicate API calls)
            start_date: Optional start date for filtering (YYYY-MM-DD)
            end_date: Optional end date for filtering (YYYY-MM-DD)
        
        Returns:
            Dictionary with relayer analysis results
        """
        # Use pre-fetched events when provided to avoid duplicate API calls
        if withdrawal_events is None:
            if contract_addresses is not None:
                if network is None:
                    network = self.network
                withdrawal_events = self.fetcher.get_withdrawal_events(contract_addresses, limit, network, start_date, end_date)
            else:
                # Use existing withdrawals if available, but they may not have relayer data from transfers
                withdrawal_events = [w for w in self.withdrawals if w.relayer]
        
        withdrawals_with_relayers = [w for w in withdrawal_events if w.relayer]
        
        if not withdrawals_with_relayers:
            return {}
        
        relayer_counts = Counter()
        relayer_fees = defaultdict(list)
        relayer_recipients = defaultdict(set)
        
        for withdrawal in withdrawals_with_relayers:
            if withdrawal.relayer and withdrawal.relayer != "0x0000000000000000000000000000000000000000":
                relayer_counts[withdrawal.relayer] += 1
                if withdrawal.fee:
                    try:
                        relayer_fees[withdrawal.relayer].append(float(withdrawal.fee) / 1e18)  # Convert wei to ETH
                    except:
                        pass
                if withdrawal.recipient:
                    relayer_recipients[withdrawal.relayer].add(withdrawal.recipient)
        
        # Calculate average fees per relayer
        avg_fees = {}
        for relayer, fees in relayer_fees.items():
            avg_fees[relayer] = sum(fees) / len(fees) if fees else 0
        
        return {
            "total_with_relayers": len(withdrawals_with_relayers),
            "unique_relayers": len(relayer_counts),
            "relayer_counts": dict(relayer_counts.most_common()),
            "relayer_avg_fees": avg_fees,
            "relayer_unique_recipients": {k: len(v) for k, v in relayer_recipients.items()}
        }
    
    def analyze_nullifiers(self, contract_addresses: List[str] = None, limit: int = 1000, network: str = None, withdrawal_events: List[TornadoTransaction] = None, start_date: Optional[str] = None, end_date: Optional[str] = None) -> Dict:
        """
        Analyze nullifier usage to detect potential double-spends
        NOTE: This requires event data (nullifier field is only available in events)
        
        Args:
            contract_addresses: List of contract addresses to query (if not provided, uses instance data)
            limit: Maximum number of transactions to retrieve
            network: Network identifier (eth, matic, bsc, etc.). Uses instance network if not provided.
            withdrawal_events: Pre-fetched withdrawal events to use (avoids duplicate API calls)
            start_date: Optional start date for filtering (YYYY-MM-DD)
            end_date: Optional end date for filtering (YYYY-MM-DD)
        
        Returns:
            Dictionary with nullifier analysis results
        """
        # Use pre-fetched events when provided to avoid duplicate API calls
        if withdrawal_events is None:
            if contract_addresses is not None:
                if network is None:
                    network = self.network
                withdrawal_events = self.fetcher.get_withdrawal_events(contract_addresses, limit, network, start_date, end_date)
            else:
                # Use existing withdrawals if available, but they may not have nullifier data from transfers
                withdrawal_events = [w for w in self.withdrawals if w.nullifier]
        
        withdrawals_with_nullifiers = [w for w in withdrawal_events if w.nullifier]
        
        if not withdrawals_with_nullifiers:
            return {}
        
        nullifier_counts = Counter()
        for withdrawal in withdrawals_with_nullifiers:
            if withdrawal.nullifier:
                nullifier_counts[withdrawal.nullifier] += 1
        
        # Find potential double-spends (same nullifier used multiple times)
        double_spends = {n: count for n, count in nullifier_counts.items() if count > 1}
        
        return {
            "total_with_nullifiers": len(withdrawals_with_nullifiers),
            "unique_nullifiers": len(nullifier_counts),
            "potential_double_spends": double_spends
        }
    
    def generate_report(self, contract_addresses: List[str] = None, limit: int = 1000, network: str = None) -> str:
        """
        Generate a comprehensive analysis report
        
        Args:
            contract_addresses: Optional list of contract addresses for fetching events (relayer/nullifier analysis)
            limit: Optional limit for fetching events
            network: Optional network identifier. Uses instance network if not provided.
        
        Returns:
            Formatted report string
        """
        if network is None:
            network = self.network
        
        report = []
        report.append("=" * 80)
        report.append("TORNADO CASH TRANSACTION ANALYSIS REPORT")
        report.append("=" * 80)
        report.append("")
        
        # Summary
        report.append(f"Total Deposits: {len(self.deposits)}")
        report.append(f"Total Withdrawals: {len(self.withdrawals)}")
        report.append("")
        
        # Deposit Analysis
        if self.deposits:
            report.append("-" * 80)
            report.append("DEPOSIT ANALYSIS")
            report.append("-" * 80)
            deposit_timestamp_analysis = self.analyze_timestamps(self.deposits)
            if deposit_timestamp_analysis:
                report.append(f"Most Active Day: {deposit_timestamp_analysis.get('most_active_day')}")
                report.append(f"Average Transactions per Day: {deposit_timestamp_analysis.get('average_per_day', 0):.2f}")
            report.append("")
        
        # Withdrawal Analysis
        if self.withdrawals:
            report.append("-" * 80)
            report.append("WITHDRAWAL ANALYSIS")
            report.append("-" * 80)
            withdrawal_timestamp_analysis = self.analyze_timestamps(self.withdrawals)
            if withdrawal_timestamp_analysis:
                report.append(f"Most Active Day: {withdrawal_timestamp_analysis.get('most_active_day')}")
                report.append(f"Average Transactions per Day: {withdrawal_timestamp_analysis.get('average_per_day', 0):.2f}")
            report.append("")
        
        # Address Reuse
        all_txs = self.deposits + self.withdrawals
        reused_addresses = self.find_address_reuse(all_txs)
        if reused_addresses:
            report.append("-" * 80)
            report.append("ADDRESS REUSE DETECTION")
            report.append("-" * 80)
            report.append(f"Found {len(reused_addresses)} addresses with multiple transactions:")
            for addr, count in list(reused_addresses.items())[:10]:  # Top 10
                report.append(f"  {addr}: {count} transactions")
            report.append("")
        
        # Matched Transactions
        matches = self.match_deposits_withdrawals()
        if matches:
            report.append("-" * 80)
            report.append("MATCHED DEPOSIT-WITHDRAWAL PAIRS")
            report.append("-" * 80)
            report.append(f"Found {len(matches)} potential matches:")
            for i, match in enumerate(matches[:10], 1):  # Top 10
                report.append(f"\nMatch {i}:")
                report.append(f"  Deposit: {match['deposit'].tx_hash}")
                report.append(f"  Withdrawal: {match['withdrawal'].tx_hash}")
                time_diff_hours = match.get("time_diff_hours", match["time_diff_days"] * 24)
                report.append(f"  Time Difference: {time_diff_hours:.2f} hours")
            report.append("")
        
        # Network Analysis
        network_analysis = self.analyze_network_patterns()
        if network_analysis:
            report.append("-" * 80)
            report.append("NETWORK PATTERN ANALYSIS")
            report.append("-" * 80)
            report.append(f"Total Unique Addresses: {network_analysis.get('total_unique_addresses', 0)}")
            report.append(f"Common Addresses Across Windows: {len(network_analysis.get('common_addresses', []))}")
            report.append("")
        
        # Relayer Analysis (from events)
        relayer_analysis = self.analyze_relayers(contract_addresses, limit, network)
        if relayer_analysis:
            report.append("-" * 80)
            report.append("RELAYER ANALYSIS")
            report.append("-" * 80)
            report.append(f"Withdrawals with Relayers: {relayer_analysis.get('total_with_relayers', 0)}")
            report.append(f"Unique Relayers: {relayer_analysis.get('unique_relayers', 0)}")
            if relayer_analysis.get('relayer_counts'):
                report.append("\nTop Relayers by Transaction Count:")
                for relayer, count in list(relayer_analysis['relayer_counts'].items())[:5]:
                    avg_fee = relayer_analysis.get('relayer_avg_fees', {}).get(relayer, 0)
                    unique_recipients = relayer_analysis.get('relayer_unique_recipients', {}).get(relayer, 0)
                    report.append(f"  {relayer}: {count} transactions, avg fee: {avg_fee:.6f} ETH, {unique_recipients} unique recipients")
            report.append("")
        
        # Nullifier Analysis (from events)
        nullifier_analysis = self.analyze_nullifiers(contract_addresses, limit, network)
        if nullifier_analysis:
            report.append("-" * 80)
            report.append("NULLIFIER ANALYSIS")
            report.append("-" * 80)
            report.append(f"Withdrawals with Nullifiers: {nullifier_analysis.get('total_with_nullifiers', 0)}")
            report.append(f"Unique Nullifiers: {nullifier_analysis.get('unique_nullifiers', 0)}")
            if nullifier_analysis.get('potential_double_spends'):
                report.append(f"⚠️  WARNING: Found {len(nullifier_analysis['potential_double_spends'])} potential double-spends!")
                for nullifier, count in list(nullifier_analysis['potential_double_spends'].items())[:5]:
                    report.append(f"  Nullifier {nullifier} used {count} times")
            report.append("")
        
        report.append("=" * 80)
        return "\n".join(report)
    
    def export_to_json(self, filename: str = "tornado_analysis.json", contract_addresses: List[str] = None, limit: int = 1000, network: str = None):
        """
        Export analysis results to JSON file
        
        Args:
            filename: Output filename
            contract_addresses: Optional list of contract addresses for fetching events (relayer/nullifier analysis)
            limit: Optional limit for fetching events
            network: Optional network identifier. Uses instance network if not provided.
        """
        if network is None:
            network = self.network
        
        data = {
            "deposits": [
                {
                    "tx_hash": tx.tx_hash,
                    "from": tx.from_address,
                    "to": tx.to_address,
                    "block_time": tx.block_time,
                    "gas": tx.gas,
                    "commitment": tx.commitment
                }
                for tx in self.deposits
            ],
            "withdrawals": [
                {
                    "tx_hash": tx.tx_hash,
                    "from": tx.from_address,
                    "to": tx.to_address,
                    "block_time": tx.block_time,
                    "gas": tx.gas,
                    "nullifier": tx.nullifier,
                    "recipient": tx.recipient,
                    "relayer": tx.relayer,
                    "fee": tx.fee
                }
                for tx in self.withdrawals
            ],
            "analysis": {
                "deposit_timestamps": self.analyze_timestamps(self.deposits),
                "withdrawal_timestamps": self.analyze_timestamps(self.withdrawals),
                "reused_addresses": self.find_address_reuse(self.deposits + self.withdrawals),
                "matched_pairs": [
                    {
                        "deposit_hash": m["deposit"].tx_hash,
                        "withdrawal_hash": m["withdrawal"].tx_hash,
                        "time_diff_days": m["time_diff_days"],
                        "time_diff_hours": m.get("time_diff_hours", m["time_diff_days"] * 24)
                    }
                    for m in self.match_deposits_withdrawals()
                ],
                "network_patterns": self.analyze_network_patterns(),
                "relayer_analysis": self.analyze_relayers(contract_addresses, limit, network),
                "nullifier_analysis": self.analyze_nullifiers(contract_addresses, limit, network)
            }
        }
        
        with open(filename, 'w') as f:
            json.dump(data, f, indent=2, default=str)
        
        print(f"Analysis exported to {filename}")

