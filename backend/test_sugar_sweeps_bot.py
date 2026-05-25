"""
Sugar Sweeps Bot Test Script

Tests P2P transfers for Juwa and Orion Stars platforms
Recipient: sugarl330 (test account)
Amount: 100 credits ($1 test)
"""

import asyncio
import sys
sys.path.append('/app/backend')

from middleware.sugar_sweeps_bridge import SugarSweepsBridge
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def test_sugar_sweeps_bot():
    """
    Test the Sugar Sweeps P2P bot with actual credentials.
    
    Flow:
    1. Initialize bot
    2. Login to sugarsweeps.com
    3. Transfer 100 credits to sugarl330 on Juwa
    4. Wait (drip injection)
    5. Transfer 100 credits to sugarl330 on Orion Stars
    """
    
    logger.info("=" * 80)
    logger.info("🚀 SUGAR SWEEPS BOT TEST - STARTING")
    logger.info("=" * 80)
    
    bridge = SugarSweepsBridge()
    
    try:
        # Step 1: Initialize (login + map platforms)
        logger.info("\n📍 Step 1: Initializing Sugar Sweeps Bridge...")
        success, msg = await bridge.initialize()
        
        if not success:
            logger.error(f"❌ Initialization failed: {msg}")
            return False
        
        logger.info(f"✅ {msg}")
        logger.info(f"💰 Master Balance: ${bridge.master_balance}")
        logger.info(f"🗺️  Platforms mapped: {len(bridge.platform_selectors)}")
        
        # Step 2: Test Juwa transfer
        logger.info("\n📍 Step 2: Testing Juwa P2P Transfer...")
        logger.info("   Recipient: sugarl330")
        logger.info("   Amount: 100 credits ($1)")
        logger.info("   Platform: Juwa")
        
        success_juwa, msg_juwa, tx_id_juwa = await bridge.transfer_credits_p2p(
            recipient_username="sugarl330",
            amount=100,
            platform="Juwa"
        )
        
        if success_juwa:
            logger.info(f"✅ Juwa transfer queued: {msg_juwa}")
            logger.info(f"   TX ID: {tx_id_juwa}")
        else:
            logger.error(f"❌ Juwa transfer failed: {msg_juwa}")
        
        # Step 3: Test Orion Stars transfer
        logger.info("\n📍 Step 3: Testing Orion Stars P2P Transfer...")
        logger.info("   Recipient: sugarl330")
        logger.info("   Amount: 100 credits ($1)")
        logger.info("   Platform: Orion Stars")
        
        success_orion, msg_orion, tx_id_orion = await bridge.transfer_credits_p2p(
            recipient_username="sugarl330",
            amount=100,
            platform="Orion Stars"
        )
        
        if success_orion:
            logger.info(f"✅ Orion Stars transfer queued: {msg_orion}")
            logger.info(f"   TX ID: {tx_id_orion}")
        else:
            logger.error(f"❌ Orion Stars transfer failed: {msg_orion}")
        
        # Step 4: Monitor queue processing
        logger.info("\n📍 Step 4: Monitoring drip injection queue...")
        logger.info(f"   Queue size: {len(bridge.transfer_queue)}")
        logger.info(f"   Processing: {bridge.processing_queue}")
        logger.info("\n⏳ Waiting for transfers to complete (drip injection active)...")
        logger.info("   This will take 45-120 seconds between transfers...")
        
        # Wait for queue to empty (max 5 minutes)
        wait_time = 0
        while bridge.transfer_queue and wait_time < 300:
            await asyncio.sleep(10)
            wait_time += 10
            logger.info(f"   ⏰ Elapsed: {wait_time}s | Queue: {len(bridge.transfer_queue)} remaining")
        
        if not bridge.transfer_queue:
            logger.info("\n✅ All transfers completed!")
        else:
            logger.warning(f"\n⚠️  Timeout reached. {len(bridge.transfer_queue)} transfers still pending.")
        
        # Step 5: Final status
        status = bridge.get_status()
        logger.info("\n" + "=" * 80)
        logger.info("📊 FINAL STATUS:")
        logger.info("=" * 80)
        logger.info(f"   Authenticated: {status['authenticated']}")
        logger.info(f"   Master Balance: ${status['master_balance']}")
        logger.info(f"   Platforms Mapped: {status['platforms_mapped']}")
        logger.info(f"   Queue Size: {status['queue_size']}")
        logger.info(f"   Session Active: {status['session_active']}")
        logger.info("=" * 80)
        
        return True
    
    except Exception as e:
        logger.error(f"\n❌ Test failed with exception: {str(e)}")
        import traceback
        traceback.print_exc()
        return False
    
    finally:
        # Cleanup
        logger.info("\n🔒 Closing browser...")
        await bridge.close()
        logger.info("✅ Test complete!")

if __name__ == "__main__":
    result = asyncio.run(test_sugar_sweeps_bot())
    sys.exit(0 if result else 1)
