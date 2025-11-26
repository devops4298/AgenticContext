#!/usr/bin/env python3
"""
main.py — Entry point for the multi-agent ADK system.

This is the main entry point that initializes the orchestrator
and handles user interaction.
"""

import os
import sys
import logging
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from tools.rag import AppConfig, RAGPipeline
from agents.orchestrator_agent import OrchestratorAgent
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger("main")


def main():
    """Main entry point for the application."""
    logger.info("Initializing multi-agent ADK system...")
    
    # Check API key
    api_key = os.getenv("GOOGLE_AI_API_KEY")
    if not api_key or api_key == "your-api-key-here":
        logger.error("GOOGLE_AI_API_KEY not set! Please set it in your .env file.")
        return 1
    
    # Initialize configuration
    cfg = AppConfig()
    
    # Initialize RAG pipeline
    logger.info("Initializing RAG pipeline...")
    pipeline = RAGPipeline(cfg)
    
    # Try to load from cache
    if not pipeline.load_from_cache():
        logger.warning("No cached index found. Please index documents first.")
        logger.info("To index documents, use: python -m rag_prod index <folder_path>")
        return 1
    
    # Initialize orchestrator
    logger.info("Initializing orchestrator agent...")
    orchestrator = OrchestratorAgent(cfg)
    orchestrator.initialize_sub_agents(pipeline)
    
    # Interactive loop
    logger.info("Multi-agent system ready!")
    logger.info("Enter your automation request (or 'quit' to exit):")
    
    while True:
        try:
            user_input = input("\n> ").strip()
            
            if user_input.lower() in ['quit', 'exit', 'q']:
                logger.info("Exiting...")
                break
            
            if not user_input:
                continue
            
            # Orchestrate request
            logger.info(f"Processing request: {user_input[:50]}...")
            result = orchestrator.orchestrate(
                user_query=user_input,
                rag_pipeline=pipeline,
                automation_tool="playwright"  # Generate Playwright script
            )
            
            # Display results
            if result.get("error"):
                logger.error(f"Error: {result.get('error')}")
                print(f"\n❌ {result.get('response')}")
            else:
                print(f"\n✅ {result.get('response')}")
                
                # Check if script was generated
                generated_script = result.get("generated_script")
                if generated_script:
                    print(f"\n📝 Generated {result.get('automation_tool', 'playwright')} script:")
                    print("=" * 80)
                    print(generated_script)
                    print("=" * 80)
                else:
                    print("\n⚠️  No script was generated.")
                    print("This might be because:")
                    print("  - No automation_tool was specified")
                    print("  - Script generation failed")
                    print("  - Check the logs for more details")
                    logger.warning("No generated_script in result")
                
                # Option to save script
                save = input("\n💾 Save script to file? (y/n): ").strip().lower()
                if save == 'y':
                    filename = input("Enter filename (default: generated_script.py): ").strip()
                    if not filename:
                        filename = "generated_script.py"
                    
                    with open(filename, 'w') as f:
                        f.write(result.get("generated_script", ""))
                    logger.info(f"Script saved to {filename}")
        
        except KeyboardInterrupt:
            logger.info("\nExiting...")
            break
        except Exception as e:
            logger.error(f"Error: {e}", exc_info=True)
            print(f"\n❌ Error: {str(e)}")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())

