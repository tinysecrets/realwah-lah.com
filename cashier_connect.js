/**
 * Frontend Transaction Controller for wah-lah.com
 * Handles the submission payload for the Cashier Workflow
 */
async function submitWithdrawalRequest() {
    // 1. Grab values directly from your UI input IDs
    const redeemAmount = parseFloat(document.getElementById("redeem_amount")?.value || 0);
    const payoutMethod = document.getElementById("payout_method")?.value;
    const walletAddress = document.getElementById("wallet_address")?.value;
    
    // Grabs active selection from the $0, $2, $5, $10 tip elements
    const tipAmount = parseFloat(window.selectedTipAmount || 0); 

    // Validation check before network hit
    if (!redeemAmount || !payoutMethod || !walletAddress) {
        alert("Please fill out all required fields.");
        return;
    }

    const payload = {
        user_id: window.currentUserId, // Pulls the active authenticated user ID session
        redeem_amount: redeemAmount,
        payout_method: payoutMethod,
        wallet_address: walletAddress,
        tip_amount: tipAmount
    };

    try {
        // 2. Route the payload directly to the running backend service
        const response = await fetch('/api/v1/payments/withdraw', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(payload)
        });

        const result = await response.json();

        if (response.ok && result.status === "success") {
            alert("Success: Your request has been logged for Cashier review.");
            window.location.reload(); // Refresh to update visible wallet balances
        } else {
            alert(`Error: ${result.message || "Failed to process request."}`);
        }
    } catch (error) {
        console.error("Payment Gateway Error:", error);
        alert("Network error: Could not connect to the payment gateway server.");
    }
}
