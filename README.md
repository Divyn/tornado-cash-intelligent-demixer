# Tornado Cash Transaction Match Finder - Intelligence Tool

A **de-mixing and attribution tool** for Tornado Cash transactions. This tool is purpose-built to match deposits to withdrawals, detecting behavioral patterns, and identifying network connections.

## Final Output

![](/img/1.png)
![](/img/2.png)
![](/img/3.png)

## Features

### Core Analysis
- **Deposit Tracking**: Retrieve and analyze all deposits to Tornado Cash contracts
- **Withdrawal Tracking**: Monitor withdrawals from Tornado Cash contracts
- **Event-Based Data**: Capture commitments (from Deposit events) and nullifiers (from Withdrawal events)

### De-Mixing & Attribution
- **Deposit-Withdrawal Matching**: Match deposits with potential withdrawals based on timing (configurable time windows)
- **Network Pattern Analysis**: Analyze connections between addresses within time windows
- **Address Reuse Detection**: Find addresses that appear in multiple transactions (privacy compromise indicator)

### Nullifier & Relayers
- **Relayer Analysis**: Track relayer usage patterns, fees, and recipient diversity
- **Nullifier Analysis**: Detect potential double-spends and withdrawal patterns



#### How does the de-mixing work?




## Installation

1. Clone this repository:
```bash
git clone https://github.com/Divyn/tornado-cash-intelligent-demixer.git
cd tornado-cash-intelligent-demixer
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Set up your Bitquery OAuth token:
   - Get your token from [Bitquery](https://account.bitquery.io/user/api_v2/access_tokens)
   - Create a `.env` file in the project root:
   ```
   BITQUERY_OAUTH_TOKEN=your_oauth_token_here
   ```
   - Alternatively, you can set it as an environment variable:
   ```bash
   export BITQUERY_OAUTH_TOKEN=your_oauth_token_here
   ```

## Usage

### Web UI (Flask)

**Start the Flask web server:**
```bash
python3 app.py
```

Then open your browser to `http://localhost:5000`

