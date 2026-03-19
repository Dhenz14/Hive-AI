#!/usr/bin/env python3
"""
scripts/run_coordinator.py

CLI entry point for the Spirit Bomb Community Coordinator.

Connects to a live HivePoA instance, polls for online compute nodes,
derives the community tier, and publishes tier manifests.

Usage:
    # Single poll cycle (for testing):
    python scripts/run_coordinator.py --hivepoa-url http://localhost:5000 --api-key <key> --once

    # Continuous polling (production):
    python scripts/run_coordinator.py --hivepoa-url http://localhost:5000 --api-key <key>

    # With custom interval:
    python scripts/run_coordinator.py --hivepoa-url http://localhost:5000 --api-key <key> --poll-interval 300
"""

import argparse
import asyncio
import logging
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from hiveai.compute.community_coordinator import CommunityCoordinator


async def run_once(coordinator: CommunityCoordinator) -> None:
    """Run a single poll cycle and exit."""
    logging.info("Running single poll cycle...")
    try:
        await coordinator._poll_cycle()
        manifest = coordinator.last_manifest
        if manifest:
            logging.info(
                f"Result: Tier {manifest.tier}, {manifest.total_gpus} GPUs, "
                f"{manifest.active_clusters} clusters, model={manifest.base_model}"
            )
        else:
            logging.info("No nodes online — no manifest published")
    except Exception as e:
        logging.error(f"Poll cycle failed: {e}", exc_info=True)
        sys.exit(1)


async def main():
    parser = argparse.ArgumentParser(
        description="Spirit Bomb Community Coordinator — tier monitoring + manifest publishing"
    )
    parser.add_argument(
        "--hivepoa-url", default="http://localhost:5000",
        help="HivePoA server URL (default: http://localhost:5000)"
    )
    parser.add_argument(
        "--api-key", default=os.environ.get("SPIRITBOMB_API_KEY", ""),
        help="API key for HivePoA authentication (ApiKey scheme). Also reads SPIRITBOMB_API_KEY env var."
    )
    parser.add_argument(
        "--poll-interval", type=int, default=900,
        help="Poll interval in seconds (default: 900 = 15 min)"
    )
    parser.add_argument(
        "--once", action="store_true",
        help="Run a single poll cycle and exit (for testing)"
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true",
        help="Enable debug logging"
    )
    args = parser.parse_args()

    level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )

    # Update coordinator to use ApiKey auth
    coordinator = CommunityCoordinator(
        hivepoa_url=args.hivepoa_url,
        api_key=args.api_key,
        poll_interval=args.poll_interval,
    )

    if args.once:
        await run_once(coordinator)
    else:
        logging.info(
            f"Starting coordinator: HivePoA={args.hivepoa_url}, "
            f"interval={args.poll_interval}s, auth={'ApiKey' if args.api_key else 'none'}"
        )
        await coordinator.run()


if __name__ == "__main__":
    asyncio.run(main())
