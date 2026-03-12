import argparse
import sys
import yaml
from pathlib import Path

def load_config(config_path: str) -> dict:
    with open(config_path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)

def main():
    parser = argparse.ArgumentParser(description='Radiological Technologist Shift Scheduler')
    parser.add_argument('--month', type=str, required=True, help='Target month (YYYY-MM)')
    parser.add_argument('--config', type=str, default='config.yaml', help='Path to config file')
    args = parser.parse_args()

    print(f"Loading configuration from {args.config}...")
    config = load_config(args.config)
    
    print(f"Starting scheduler for {args.month}...")
    # TODO: Implement scheduling logic
    
    print("Done.")

if __name__ == "__main__":
    main()
