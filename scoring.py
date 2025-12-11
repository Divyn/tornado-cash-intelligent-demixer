"""
Scoring module for Tornado Cash deposit-withdrawal matching

This module contains the scoring logic used to rank potential matches
between deposits and withdrawals. Lower scores indicate better matches.
"""

from typing import Optional


def calculate_match_score(
    time_diff_seconds: float,
    tolerance_seconds: float,
    deposit_value: Optional[float],
    withdrawal_value: Optional[float],
    same_contract: bool,
    same_pool: bool,
) -> float:
    """
    Calculate a match score for a deposit-withdrawal pair.
    
    Lower scores indicate better matches. The score is calculated based on:
    - Time proximity (closer times = lower score)
    - Amount similarity (closer amounts = lower score)
    - Contract match (same contract = lower score)
    - Pool match (same pool = lower score)
    
    Args:
        time_diff_seconds: Time difference between deposit and withdrawal in seconds
        tolerance_seconds: Maximum allowed time difference (used for normalization)
        deposit_value: Value of the deposit transaction
        withdrawal_value: Value of the withdrawal transaction
        same_contract: Whether deposit and withdrawal use the same contract
        same_pool: Whether deposit and withdrawal use the same pool denomination
        
    Returns:
        Match score (lower is better)
    """
    # Time score: normalized to 0-1 range (lower is better)
    time_score = time_diff_seconds / tolerance_seconds if tolerance_seconds > 0 else 1.0
    
    # Amount score: percentage difference (lower is better)
    if deposit_value and deposit_value > 0:
        amount_score = abs(deposit_value - withdrawal_value) / deposit_value if withdrawal_value else 1.0
    else:
        amount_score = 1.0
    
    # Contract bonus: penalty for different contracts
    contract_bonus = 0.0 if same_contract else 0.3
    
    # Pool bonus: larger penalty for different pools
    pool_bonus = 0.0 if same_pool else 0.5
    
    # Total score (lower is better)
    score = time_score + amount_score + contract_bonus + pool_bonus
    
    return score


def check_amount_match(
    deposit_value: Optional[float],
    withdrawal_value: Optional[float],
    value_tolerance_percent: float = 0.05,
) -> bool:
    """
    Check if deposit and withdrawal amounts match within tolerance.
    
    Args:
        deposit_value: Value of the deposit transaction
        withdrawal_value: Value of the withdrawal transaction
        value_tolerance_percent: Percentage tolerance for amount matching (default 5%)
        
    Returns:
        True if amounts match within tolerance, False otherwise
    """
    if not deposit_value or not withdrawal_value:
        return False
    
    # Withdrawal should be <= deposit (due to relayer fees)
    # But allow some tolerance for rounding/calculation differences
    if withdrawal_value <= deposit_value * (1 + value_tolerance_percent):
        # Prefer closer matches
        amount_diff_percent = abs(deposit_value - withdrawal_value) / deposit_value if deposit_value > 0 else 1.0
        return amount_diff_percent <= value_tolerance_percent
    
    return False
