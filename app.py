#!/usr/bin/env python3
"""
Flask UI for Tornado Cash Analyzer
"""

from flask import Flask, render_template, jsonify, request, Response
import sys
import csv
import io
from tornado_analyzer import TornadoCashAnalyzer
import config

app = Flask(__name__)


def get_analyzer(network: str = "eth"):
    """Get analyzer instance with OAuth token"""
    token = config.BITQUERY_OAUTH_TOKEN
    if not token:
        raise ValueError("BITQUERY_OAUTH_TOKEN not set. Please create a .env file.")
    return TornadoCashAnalyzer(oauth_token=token, network=network)


@app.route('/')
def index():
    """Main page"""
    return render_template('index.html')


def _serialize_deposits(analyzer: TornadoCashAnalyzer, network: str):
    """Convert deposits on the analyzer to JSON-serializable dicts"""
    return [{
        'tx_hash': tx.tx_hash,
        'from_address': tx.from_address,
        'to_address': tx.to_address,
        'block_time': tx.block_time,
        'gas': tx.gas,
        'commitment': tx.commitment,
        'transaction_type': tx.transaction_type,
        'value': tx.value,
        'pool_denomination': config.get_pool_denomination(tx.to_address, network)
    } for tx in analyzer.deposits]


def _serialize_withdrawals(analyzer: TornadoCashAnalyzer, network: str):
    """Convert withdrawals on the analyzer to JSON-serializable dicts"""
    return [{
        'tx_hash': tx.tx_hash,
        'from_address': tx.from_address,
        'to_address': tx.to_address,
        'block_time': tx.block_time,
        'gas': tx.gas,
        'nullifier': tx.nullifier,
        'recipient': tx.recipient,
        'relayer': tx.relayer,
        'fee': tx.fee,
        'transaction_type': tx.transaction_type,
        # Withdrawals originate from the pool, so use from_address (pool) for labels
        'pool_denomination': config.get_pool_denomination(tx.from_address, network)
    } for tx in analyzer.withdrawals]


def _build_matched_pairs(analyzer: TornadoCashAnalyzer):
    """Standardize matched pair payload"""
    matched = []
    for m in analyzer.match_deposits_withdrawals():
        matched.append({
            'deposit_hash': m['deposit'].tx_hash,
            'withdrawal_hash': m['withdrawal'].tx_hash,
            'time_diff_days': m['time_diff_days'],
            'time_diff_hours': m.get('time_diff_hours', m['time_diff_days'] * 24),
            'deposit_from': m['deposit'].from_address,
            'withdrawal_to': m['withdrawal'].to_address or m['withdrawal'].recipient,
            'amount_match': m.get('amount_match', False),
            'same_contract': m.get('same_contract', False),
            'same_pool': m.get('same_pool', False),
            'deposit_pool': m.get('deposit_pool', 'Unknown'),
            'withdrawal_pool': m.get('withdrawal_pool', 'Unknown')
        })
    return matched


@app.route('/api/fetch', methods=['POST'])
def fetch_data():
    """Fetch tornado cash data"""
    try:
        data = request.get_json() or {}
        limit = data.get('limit', 100)
        network = data.get('network', 'eth')
        contracts = data.get('contracts')
        start_date = data.get('start_date') or data.get('startDate')
        end_date = data.get('end_date') or data.get('endDate')
        if not contracts:
            contracts = config.get_tornado_cash_addresses(network)
        
        analyzer = get_analyzer(network=network)
        
        # Fetch deposits and withdrawals via transfers (for match finder, deposits tab, withdrawals tab, address reuse, timestamp analysis)
        analyzer.get_deposits(contracts, limit=limit, network=network, start_date=start_date, end_date=end_date)
        analyzer.get_withdrawals(contracts, limit=limit, network=network, start_date=start_date, end_date=end_date)
        print(f"Fetched {len(analyzer.deposits)} deposits, {len(analyzer.withdrawals)} withdrawals via transfers")
        
        # Convert transactions to dictionaries
        deposits_data = _serialize_deposits(analyzer, network)
        withdrawals_data = _serialize_withdrawals(analyzer, network)
        
        # Generate analysis (heavy relayer/nullifier analysis handled by separate route)
        analysis = {
            'deposit_timestamps': analyzer.analyze_timestamps(analyzer.deposits),
            'withdrawal_timestamps': analyzer.analyze_timestamps(analyzer.withdrawals),
            'reused_addresses': analyzer.find_address_reuse(analyzer.deposits + analyzer.withdrawals),
            'matched_pairs': _build_matched_pairs(analyzer),
            'network_patterns': analyzer.analyze_network_patterns()
        }
        
        return jsonify({
            'success': True,
            'deposits': deposits_data,
            'withdrawals': withdrawals_data,
            'analysis': analysis,
            'summary': {
                'total_deposits': len(deposits_data),
                'total_withdrawals': len(withdrawals_data)
            }
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/summary', methods=['POST'])
def fetch_summary():
    """Fetch only summary + analysis (no large tables)"""
    try:
        data = request.get_json() or {}
        limit = data.get('limit', 100)
        network = data.get('network', 'eth')
        contracts = data.get('contracts')
        start_date = data.get('start_date') or data.get('startDate')
        end_date = data.get('end_date') or data.get('endDate')
        if not contracts:
            contracts = config.get_tornado_cash_addresses(network)

        analyzer = get_analyzer(network=network)
        # Fetch deposits and withdrawals via transfers (for match finder, address reuse, timestamp analysis)
        analyzer.get_deposits(contracts, limit=limit, network=network, start_date=start_date, end_date=end_date)
        analyzer.get_withdrawals(contracts, limit=limit, network=network, start_date=start_date, end_date=end_date)

        analysis = {
            'deposit_timestamps': analyzer.analyze_timestamps(analyzer.deposits),
            'withdrawal_timestamps': analyzer.analyze_timestamps(analyzer.withdrawals),
            'reused_addresses': analyzer.find_address_reuse(analyzer.deposits + analyzer.withdrawals),
            'matched_pairs': _build_matched_pairs(analyzer),
            'network_patterns': analyzer.analyze_network_patterns()
        }

        return jsonify({
            'success': True,
            'analysis': analysis,
            'summary': {
                'total_deposits': len(analyzer.deposits),
                'total_withdrawals': len(analyzer.withdrawals)
            }
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/deposits', methods=['POST'])
def fetch_deposits():
    """Fetch only deposit rows (lazy-loaded)"""
    try:
        data = request.get_json() or {}
        limit = data.get('limit', 100)
        network = data.get('network', 'eth')
        contracts = data.get('contracts')
        start_date = data.get('start_date') or data.get('startDate')
        end_date = data.get('end_date') or data.get('endDate')
        if not contracts:
            contracts = config.get_tornado_cash_addresses(network)

        analyzer = get_analyzer(network=network)
        # Use transfers for deposits tab
        analyzer.get_deposits(contracts, limit=limit, network=network, start_date=start_date, end_date=end_date)
        deposits_data = _serialize_deposits(analyzer, network)

        return jsonify({
            'success': True,
            'deposits': deposits_data,
            'count': len(deposits_data)
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/withdrawals', methods=['POST'])
def fetch_withdrawals():
    """Fetch only withdrawal rows (lazy-loaded)"""
    try:
        data = request.get_json() or {}
        limit = data.get('limit', 100)
        network = data.get('network', 'eth')
        contracts = data.get('contracts')
        start_date = data.get('start_date') or data.get('startDate')
        end_date = data.get('end_date') or data.get('endDate')
        if not contracts:
            contracts = config.get_tornado_cash_addresses(network)

        analyzer = get_analyzer(network=network)
        # Use transfers for withdrawals tab
        analyzer.get_withdrawals(contracts, limit=limit, network=network, start_date=start_date, end_date=end_date)
        withdrawals_data = _serialize_withdrawals(analyzer, network)

        return jsonify({
            'success': True,
            'withdrawals': withdrawals_data,
            'count': len(withdrawals_data)
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/relayer-nullifier-analysis', methods=['POST'])
def fetch_relayer_nullifier_analysis():
    """Fetch relayer and nullifier analysis (non-blocking, separate route)"""
    try:
        data = request.get_json() or {}
        limit = data.get('limit', 100)
        network = data.get('network', 'eth')
        contracts = data.get('contracts')
        start_date = data.get('start_date') or data.get('startDate')
        end_date = data.get('end_date') or data.get('endDate')
        if not contracts:
            contracts = config.get_tornado_cash_addresses(network)

        analyzer = get_analyzer(network=network)
        # For relayer and nullifier analysis, fetch events separately (they require event data)
        relayer_analysis = analyzer.analyze_relayers(contracts, limit=limit, network=network, start_date=start_date, end_date=end_date)
        nullifier_analysis = analyzer.analyze_nullifiers(contracts, limit=limit, network=network, start_date=start_date, end_date=end_date)

        return jsonify({
            'success': True,
            'relayer_analysis': relayer_analysis,
            'nullifier_analysis': nullifier_analysis
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/matched-pairs.csv')
def download_matched_pairs_csv():
    """Download matched deposit-withdrawal pairs as CSV"""
    try:
        network = request.args.get('network', 'eth')
        limit = int(request.args.get('limit', 100))
        contracts = request.args.getlist('contracts')
        start_date = request.args.get('start_date') or request.args.get('startDate')
        end_date = request.args.get('end_date') or request.args.get('endDate')
        if not contracts:
            contracts = config.get_tornado_cash_addresses(network)

        analyzer = get_analyzer(network=network)
        analyzer.get_deposits(contracts, limit=limit, network=network, start_date=start_date, end_date=end_date)
        analyzer.get_withdrawals(contracts, limit=limit, network=network, start_date=start_date, end_date=end_date)
        matched_pairs = _build_matched_pairs(analyzer)

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([
            'deposit_hash',
            'deposit_from',
            'withdrawal_hash',
            'withdrawal_to',
            'deposit_pool',
            'withdrawal_pool',
            'time_diff_hours',
            'amount_match',
            'same_contract',
            'same_pool'
        ])

        for m in matched_pairs:
            time_diff_hours = m.get('time_diff_hours') or ((m.get('time_diff_days') or 0) * 24)
            writer.writerow([
                m.get('deposit_hash', ''),
                m.get('deposit_from', ''),
                m.get('withdrawal_hash', ''),
                m.get('withdrawal_to', ''),
                m.get('deposit_pool', ''),
                m.get('withdrawal_pool', ''),
                f"{time_diff_hours:.2f}" if time_diff_hours is not None else '',
                'yes' if m.get('amount_match') else 'no',
                'yes' if m.get('same_contract') else 'no',
                'yes' if m.get('same_pool') else 'no',
            ])

        csv_data = output.getvalue()
        output.close()
        filename = f"matched_pairs_{network}.csv"
        return Response(
            csv_data,
            mimetype='text/csv',
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/report')
def get_report():
    """Get text report"""
    try:
        network = request.args.get('network', 'eth')
        analyzer = get_analyzer(network=network)
        contracts = request.args.getlist('contracts')
        start_date = request.args.get('start_date') or request.args.get('startDate')
        end_date = request.args.get('end_date') or request.args.get('endDate')
        if not contracts:
            contracts = config.get_tornado_cash_addresses(network)
        limit = int(request.args.get('limit', 100))
        
        # Fetch deposits and withdrawals via transfers (for match finder, address reuse, timestamp analysis)
        analyzer.get_deposits(contracts, limit=limit, network=network, start_date=start_date, end_date=end_date)
        analyzer.get_withdrawals(contracts, limit=limit, network=network, start_date=start_date, end_date=end_date)
        
        # generate_report() will call analyze_relayers() and analyze_nullifiers()
        # with contract addresses to fetch events separately when needed
        report = analyzer.generate_report(contracts, limit, network)
        return jsonify({
            'success': True,
            'report': report
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)

