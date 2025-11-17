#!/usr/bin/env python3
"""
Agentic Streamlit app for RAG pipeline with Playwright script generation.

This app uses an orchestrator agent (root_agent) to:
1. Understand context from indexed documents
2. Coordinate specialized RAG agents
3. Generate Playwright-based automation scripts based on user requests

Run with: streamlit run rag_streamlit_app.py
"""

import os
import sys
import streamlit as st
from pathlib import Path

# Fix OpenMP conflict before importing other modules
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
os.environ.setdefault("OMP_NUM_THREADS", "1")

# Import the RAG pipeline components and orchestrator
from rag_prod import RAGPipeline, AppConfig
from orchestrator_agent import OrchestratorAgent
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Page config
st.set_page_config(
    page_title="Agentic RAG - Playwright Script Generator",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Initialize session state
if 'pipeline' not in st.session_state:
    st.session_state.pipeline = None
if 'orchestrator' not in st.session_state:
    st.session_state.orchestrator = None
if 'repo_url' not in st.session_state:
    st.session_state.repo_url = None
if 'folder_path' not in st.session_state:
    st.session_state.folder_path = None
if 'index_loaded' not in st.session_state:
    st.session_state.index_loaded = False
if 'index_metadata' not in st.session_state:
    st.session_state.index_metadata = None
if 'query_history' not in st.session_state:
    st.session_state.query_history = []
if 'generated_scripts' not in st.session_state:
    st.session_state.generated_scripts = []


def auto_load_existing_index():
    """Automatically load existing index on app startup."""
    try:
        import json
        import os
        from rag_config import DEFAULT_INDEX_METADATA_PATH, DEFAULT_CACHE_DIR
        
        # Check if index metadata exists
        if os.path.exists(DEFAULT_INDEX_METADATA_PATH):
            with open(DEFAULT_INDEX_METADATA_PATH, "r") as f:
                index_metadata = json.load(f)
            
            st.session_state.index_metadata = index_metadata
            indexed_source = index_metadata.get("indexed_source", "")
            indexed_path = index_metadata.get("indexed_folder_path", "")
            repo_url = index_metadata.get("repo_url", "")
            
            # Try to load pipeline from cache
            if indexed_source == "local_folder" and indexed_path:
                st.session_state.folder_path = indexed_path
                cfg = AppConfig()
                pipeline = RAGPipeline(cfg)
                
                # Load from cache without validation (we trust existing metadata)
                if pipeline.load_from_cache(expected_folder_path=None):  # Don't validate, just load
                    if pipeline.metadata and pipeline.indexer.index:
                        st.session_state.pipeline = pipeline
                        st.session_state.index_loaded = True
                        
                        # Initialize orchestrator
                        if not st.session_state.orchestrator:
                            st.session_state.orchestrator = OrchestratorAgent(cfg)
                        
                        return True
            
            elif indexed_source == "github_repo" and repo_url:
                st.session_state.repo_url = repo_url
                cfg = AppConfig()
                pipeline = RAGPipeline(cfg)
                
                # Load from cache
                if pipeline.load_from_cache(expected_folder_path=None):
                    if pipeline.metadata and pipeline.indexer.index:
                        st.session_state.pipeline = pipeline
                        st.session_state.index_loaded = True
                        
                        # Initialize orchestrator
                        if not st.session_state.orchestrator:
                            st.session_state.orchestrator = OrchestratorAgent(cfg)
                        
                        return True
        
        return False
    except Exception as e:
        # Silently fail on auto-load - user can manually load
        return False


# Auto-load existing index on startup
if st.session_state.pipeline is None and not st.session_state.index_loaded:
    auto_load_existing_index()


def initialize_pipeline_from_folder(folder_path: str, force_reindex: bool = False, incremental: bool = False):
    """Initialize RAG pipeline from a local folder path.
    
    Args:
        folder_path: Path to folder to index
        force_reindex: If True, delete existing index and reindex from scratch
        incremental: If True, add new files to existing index (not implemented yet, treats as new index)
    """
    try:
        with st.spinner("Initializing RAG pipeline from folder..."):
            cfg = AppConfig()
            pipeline = RAGPipeline(cfg)
            
            if force_reindex:
                # Clear existing index and start fresh
                with st.spinner(f"Clearing existing index and indexing folder: {folder_path}..."):
                    pipeline.ingest_folder(folder_path, reindex=True)
                st.success(f"✅ Folder indexed successfully! ({len(pipeline.metadata)} chunks)")
                st.session_state.index_loaded = True
            else:
                # Check if cache matches this folder
                cache_loaded = pipeline.load_from_cache(expected_folder_path=folder_path)
                if cache_loaded and pipeline.metadata and pipeline.indexer.index:
                    st.success(f"✅ Loaded existing index: {len(pipeline.metadata)} chunks")
                    st.session_state.index_loaded = True
                else:
                    # Cache doesn't match or doesn't exist - need to decide: replace or add?
                    if cache_loaded == False and st.session_state.index_loaded:
                        # We have a different index loaded - ask what to do
                        st.warning(f"⚠️ Different index found. Use 'Replace Index' to reindex this folder.")
                        return None
                    else:
                        # No existing index or first time - just index
                        st.info(f"📂 Indexing folder: {folder_path}...")
                        with st.spinner("Indexing..."):
                            try:
                                pipeline.ingest_folder(folder_path, reindex=True)
                                st.success(f"✅ Folder indexed successfully! ({len(pipeline.metadata)} chunks)")
                                st.session_state.index_loaded = True
                            except Exception as e:
                                st.error(f"❌ Error indexing folder: {str(e)}")
                                st.exception(e)
                                return None
            
            st.session_state.pipeline = pipeline
            st.session_state.folder_path = folder_path
            
            # Update index metadata in session state
            import json
            import os
            if os.path.exists(cfg.index_metadata_path):
                with open(cfg.index_metadata_path, "r") as f:
                    st.session_state.index_metadata = json.load(f)
            
            # Initialize orchestrator agent (root_agent)
            if not st.session_state.orchestrator:
                with st.spinner("Initializing orchestrator agent..."):
                    st.session_state.orchestrator = OrchestratorAgent(cfg)
                    st.success("✅ Orchestrator agent ready")
            
            return pipeline
    except Exception as e:
        st.error(f"❌ Error initializing pipeline: {str(e)}")
        st.exception(e)
        return None


def initialize_pipeline(repo_url: str, force_reindex: bool = False):
    """Initialize or reload the RAG pipeline from GitHub repository."""
    try:
        with st.spinner("Initializing RAG pipeline..."):
            cfg = AppConfig()
            pipeline = RAGPipeline(cfg)
            
            if force_reindex:
                with st.spinner(f"Cloning and indexing repository: {repo_url}..."):
                    pipeline.ingest_repo(repo_url, force_clone=True, reindex=True)
                st.success(f"✅ Repository indexed successfully! ({len(pipeline.metadata)} chunks)")
                st.session_state.index_loaded = True
            else:
                try:
                    pipeline.load_from_cache()
                    if pipeline.metadata and pipeline.indexer.index:
                        st.success(f"✅ Loaded cache: {len(pipeline.metadata)} chunks")
                        st.session_state.index_loaded = True
                    else:
                        with st.spinner(f"Cloning and indexing repository: {repo_url}..."):
                            pipeline.ingest_repo(repo_url, force_clone=False, reindex=True)
                        st.success(f"✅ Repository indexed successfully! ({len(pipeline.metadata)} chunks)")
                        st.session_state.index_loaded = True
                except Exception as e:
                    st.warning(f"Cache not found. Cloning and indexing repository: {repo_url}...")
                    with st.spinner("Cloning and indexing..."):
                        pipeline.ingest_repo(repo_url, force_clone=False, reindex=True)
                    st.success(f"✅ Repository indexed successfully! ({len(pipeline.metadata)} chunks)")
                    st.session_state.index_loaded = True
            
            st.session_state.pipeline = pipeline
            st.session_state.repo_url = repo_url
            
            # Initialize orchestrator agent (root_agent)
            if not st.session_state.orchestrator:
                with st.spinner("Initializing orchestrator agent..."):
                    st.session_state.orchestrator = OrchestratorAgent(cfg)
                    st.success("✅ Orchestrator agent ready")
            
            return pipeline
    except Exception as e:
        st.error(f"❌ Error initializing pipeline: {str(e)}")
        st.exception(e)
        return None


def query_with_orchestrator(user_query: str, generate_script: bool = False):
    """Query using orchestrator agent with optional Playwright script generation."""
    if not st.session_state.pipeline:
        st.error("❌ Pipeline not initialized. Please configure repository/folder first.")
        return None
    
    if not st.session_state.orchestrator:
        st.error("❌ Orchestrator agent not initialized.")
        return None
    
    try:
        with st.spinner("Orchestrating request..."):
            # Always get context from RAG system for better script generation
            rag_context = None
            with st.spinner("Retrieving context from indexed documents..."):
                rag_result = st.session_state.pipeline.query(user_query, top_k=40)
                rag_context = rag_result
            
            # Use orchestrator to coordinate agents and generate script if needed
            result = st.session_state.orchestrator.orchestrate(
                user_query=user_query,
                rag_context=rag_context,
                rag_pipeline=st.session_state.pipeline
            )
            
            # If script generation was requested but not generated, force it
            if generate_script and not result.get("generated_script"):
                with st.spinner("Generating Playwright script..."):
                    script_context = result.get("enhanced_context", "")
                    if not script_context and rag_context:
                        script_context = st.session_state.orchestrator._format_rag_result_for_script_generation(rag_context)
                    
                    generated_script = st.session_state.orchestrator.generate_playwright_script(
                        user_request=user_query,
                        context=script_context,
                        script_type="interaction"
                    )
                    result["generated_script"] = generated_script
                    if not result.get("response"):
                        result["response"] = "Generated Playwright script based on your request and retrieved context."
            
            return result
    except Exception as e:
        st.error(f"❌ Error orchestrating request: {str(e)}")
        st.exception(e)
        return None


# Sidebar for configuration
with st.sidebar:
    st.header("⚙️ Configuration")
    
    # Show current index status
    if st.session_state.index_metadata:
        st.subheader("📊 Current Index")
        metadata = st.session_state.index_metadata
        indexed_source = metadata.get("indexed_source", "unknown")
        if indexed_source == "local_folder":
            indexed_path = metadata.get("indexed_folder_path", "")
            num_chunks = metadata.get("num_chunks", 0)
            num_files = metadata.get("num_files", 0)
            indexed_at = metadata.get("indexed_at", "")
            st.success(f"✅ **Indexed:** `{os.path.basename(indexed_path) if indexed_path else 'Unknown'}`")
            st.caption(f"📍 {indexed_path[:50]}..." if len(indexed_path) > 50 else f"📍 {indexed_path}")
            if num_chunks:
                st.metric("Chunks", num_chunks)
            if num_files:
                st.metric("Files", num_files)
            if indexed_at:
                from datetime import datetime
                try:
                    dt = datetime.fromisoformat(indexed_at.replace('Z', '+00:00'))
                    st.caption(f"Indexed: {dt.strftime('%Y-%m-%d %H:%M')}")
                except:
                    st.caption(f"Indexed: {indexed_at[:19]}")
        elif indexed_source == "github_repo":
            repo_url = metadata.get("repo_url", "")
            num_chunks = metadata.get("num_chunks", 0)
            indexed_at = metadata.get("indexed_at", "")
            st.success(f"✅ **Indexed:** GitHub Repository")
            st.caption(f"🔗 {repo_url}")
            if num_chunks:
                st.metric("Chunks", num_chunks)
            if indexed_at:
                from datetime import datetime
                try:
                    dt = datetime.fromisoformat(indexed_at.replace('Z', '+00:00'))
                    st.caption(f"Indexed: {dt.strftime('%Y-%m-%d %H:%M')}")
                except:
                    st.caption(f"Indexed: {indexed_at[:19]}")
        
        st.divider()
    
    # Index Management
    st.subheader("📂 Index Management")
    
    # Input mode selection
    input_mode = st.radio(
        "Index Source",
        ["📁 Local Folder", "🌐 GitHub URL"],
        help="Choose to index from a local folder or clone from GitHub"
    )
    
    if input_mode == "📁 Local Folder":
        folder_path = st.text_input(
            "Folder Path",
            value=st.session_state.get("folder_path", ""),
            help="Enter the absolute or relative path to the folder containing your files",
            placeholder="/path/to/your/project or ./my_project"
        )
        
        st.caption("💡 Tip: Use absolute paths for best results")
        
        col1, col2 = st.columns(2)
        with col1:
            if st.session_state.index_loaded:
                load_btn = st.button("➕ Add to Index", use_container_width=True, 
                                    help="Add files from this folder to existing index")
            else:
                load_btn = st.button("📂 Index Folder", type="primary", use_container_width=True,
                                    help="Create new index from this folder")
        with col2:
            replace_btn = st.button("🔄 Replace Index", use_container_width=True,
                                   help="Delete existing index and create new one from this folder")
        
        if load_btn:
            if folder_path:
                st.session_state.folder_path = folder_path
                if os.path.exists(folder_path) and os.path.isdir(folder_path):
                    # If index exists, check if same folder
                    if st.session_state.index_loaded and st.session_state.index_metadata:
                        current_path = st.session_state.index_metadata.get("indexed_folder_path", "")
                        if os.path.abspath(folder_path) == os.path.abspath(current_path):
                            st.info("ℹ️ This folder is already indexed. Use 'Replace Index' to reindex.")
                        else:
                            st.warning("⚠️ Different folder. Use 'Replace Index' to switch to this folder.")
                    else:
                        # No existing index or different - create new
                        initialize_pipeline_from_folder(folder_path, force_reindex=False)
                else:
                    st.error(f"❌ Folder not found: {folder_path}")
            else:
                st.error("Please enter a folder path")
        
        if replace_btn:
            if folder_path:
                st.session_state.folder_path = folder_path
                if os.path.exists(folder_path) and os.path.isdir(folder_path):
                    initialize_pipeline_from_folder(folder_path, force_reindex=True)
                else:
                    st.error(f"❌ Folder not found: {folder_path}")
            else:
                st.error("Please enter a folder path")
    
    else:  # GitHub URL mode
        repo_url = st.text_input(
            "GitHub Repository URL",
            value=st.session_state.repo_url or "https://github.com/openai/openai-cookbook",
            help="Enter the GitHub repository URL to clone and index"
        )
        
        col1, col2 = st.columns(2)
        with col1:
            if st.session_state.index_loaded:
                load_btn = st.button("📂 Load Index", use_container_width=True,
                                    help="Load existing index for this repository")
            else:
                load_btn = st.button("📂 Index Repo", type="primary", use_container_width=True,
                                    help="Create new index from this repository")
        with col2:
            replace_btn = st.button("🔄 Replace Index", use_container_width=True,
                                   help="Delete existing index and create new one from this repository")
        
        if load_btn:
            if repo_url:
                if st.session_state.index_loaded and st.session_state.index_metadata:
                    current_repo = st.session_state.index_metadata.get("repo_url", "")
                    if repo_url == current_repo:
                        st.info("ℹ️ This repository is already indexed. Use 'Replace Index' to reindex.")
                    else:
                        st.warning("⚠️ Different repository. Use 'Replace Index' to switch to this repository.")
                else:
                    initialize_pipeline(repo_url, force_reindex=False)
            else:
                st.error("Please enter a repository URL")
        
        if replace_btn:
            if repo_url:
                initialize_pipeline(repo_url, force_reindex=True)
            else:
                st.error("Please enter a repository URL")
    
    # Clear Index Option
    if st.session_state.index_loaded:
        st.divider()
        if st.button("🗑️ Clear Index", use_container_width=True, type="secondary",
                    help="Clear current index and start fresh"):
            import shutil
            from rag_config import DEFAULT_CACHE_DIR
            try:
                # Clear session state
                st.session_state.pipeline = None
                st.session_state.index_loaded = False
                st.session_state.index_metadata = None
                st.session_state.folder_path = None
                st.session_state.repo_url = None
                st.session_state.orchestrator = None
                
                # Clear cache directory
                if os.path.exists(DEFAULT_CACHE_DIR):
                    shutil.rmtree(DEFAULT_CACHE_DIR)
                    os.makedirs(DEFAULT_CACHE_DIR, exist_ok=True)
                
                st.success("✅ Index cleared successfully!")
                st.rerun()
            except Exception as e:
                st.error(f"❌ Error clearing index: {str(e)}")
    
    st.divider()
    
    # Query settings
    st.subheader("🔧 Query Settings")
    top_k = st.slider(
        "Top K Results",
        min_value=5,
        max_value=100,
        value=40,
        step=5,
        help="Number of chunks to retrieve"
    )
    
    use_summaries = st.checkbox(
        "Use Summaries",
        value=True,
        help="Use compressed summaries for most chunks, full text for top results"
    )
    
    if st.session_state.pipeline:
        st.session_state.pipeline.cfg.top_k = top_k
    
    st.divider()
    
    # Pipeline status
    st.subheader("🔧 Status")
    if st.session_state.pipeline and st.session_state.index_loaded:
        st.success("✅ **Pipeline Ready**")
        if st.session_state.orchestrator:
            st.success("✅ **Orchestrator Ready**")
        if st.session_state.pipeline.metadata:
            num_chunks = len(st.session_state.pipeline.metadata)
            st.metric("Total Chunks", num_chunks)
            if st.session_state.pipeline.indexer.index:
                st.metric("Index Size", st.session_state.pipeline.indexer.index.ntotal)
    else:
        st.info("ℹ️ **No index loaded** - Index a folder or repository to get started")


# Main content area
st.title("🤖 Agentic RAG - Playwright Script Generator")
st.markdown("**Intelligent RAG system with orchestrator agent for context understanding and Playwright automation script generation**")

# Check API key
api_key = os.getenv("GOOGLE_AI_API_KEY")
if not api_key or api_key == "your-api-key-here":
    st.error("⚠️ **GOOGLE_AI_API_KEY not set!** Please set it in your `.env` file.")
    st.stop()

# Current source info
if st.session_state.index_loaded and st.session_state.index_metadata:
    metadata = st.session_state.index_metadata
    if metadata.get("indexed_source") == "local_folder":
        indexed_path = metadata.get("indexed_folder_path", "")
        st.success(f"📁 **Indexed Folder:** `{indexed_path}` | **Chunks:** {metadata.get('num_chunks', 0)}")
    elif metadata.get("indexed_source") == "github_repo":
        repo_url = metadata.get("repo_url", "")
        st.success(f"📚 **Indexed Repository:** `{repo_url}` | **Chunks:** {metadata.get('num_chunks', 0)}")
elif st.session_state.folder_path:
    st.info(f"📁 Current Folder: `{st.session_state.folder_path}`")
elif st.session_state.repo_url:
    st.info(f"📚 Current Repository: `{st.session_state.repo_url}`")
else:
    st.info("ℹ️ **No index loaded.** Use the sidebar to index a folder or repository.")

# Query input
st.subheader("💬 Ask a Question or Request Playwright Script")
query = st.text_area(
    "Enter your query:",
    placeholder="Example queries:\n- 'How do I implement authentication?'\n- 'Generate a Playwright script to automate form filling on example.com'\n- 'Create a script to scrape product data from an e-commerce site'",
    height=120,
    key="query_input"
)

col1, col2 = st.columns([1, 3])
with col1:
    generate_script = st.checkbox(
        "Generate Playwright Script",
        value=False,
        help="If checked, the orchestrator will generate a Playwright automation script based on your query and context"
    )
with col2:
    submit_btn = st.button("🚀 Query", type="primary", use_container_width=True)

# Process query
if submit_btn and query:
    if not st.session_state.pipeline:
        st.warning("⚠️ Pipeline not initialized. Please index a folder or repository first.")
        st.stop()
    
    if st.session_state.pipeline and st.session_state.orchestrator:
        # Use orchestrator agent
        result = query_with_orchestrator(query, generate_script=generate_script or generate_script)
        
        if result:
            # Add to query history
            st.session_state.query_history.insert(0, {
                "query": query,
                "result": result,
                "timestamp": "now"
            })
            
            # Display orchestrator response
            if result.get("response"):
                st.header("📝 Orchestrator Response")
                st.markdown(result["response"])
            
            # Display RAG answer if available
            if result.get("rag_result"):
                rag_result = result["rag_result"]
                st.header("📚 Context from RAG System")
                st.markdown(rag_result.get("answer", ""))
                
                with st.expander("📊 Retrieval Metadata"):
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        st.metric("Retrieved Chunks", len(rag_result.get("retrieved", [])))
                    with col2:
                        st.metric("Expanded Chunks", len(rag_result.get("expanded_indices_local", [])))
                    with col3:
                        st.metric("Compressed Summaries", len(rag_result.get("compressed", [])))
            
            # Display generated Playwright script
            if result.get("generated_script"):
                st.header("🎭 Generated Playwright Script")
                script = result["generated_script"]
                
                # Save script to history
                st.session_state.generated_scripts.insert(0, {
                    "query": query,
                    "script": script,
                    "timestamp": "now"
                })
                
                # Display script with download option
                st.code(script, language="python")
                
                # Download button
                st.download_button(
                    label="📥 Download Script",
                    data=script,
                    file_name="playwright_script.py",
                    mime="text/x-python"
                )
                
                # Instructions
                st.info("💡 **Next Steps:**\n1. Install Playwright: `pip install playwright`\n2. Install browsers: `playwright install`\n3. Run the script: `python playwright_script.py`")
            
            # Display function calls if any
            if result.get("function_calls"):
                with st.expander("🔧 Orchestrator Function Calls"):
                    for i, func_call in enumerate(result["function_calls"], 1):
                        st.json({
                            "function": func_call.get("name"),
                            "arguments": func_call.get("args", {})
                        })
            
            # Display enhanced context if available
            if result.get("enhanced_context"):
                with st.expander("📖 Enhanced Context for Script Generation"):
                    st.markdown(result["enhanced_context"])

# Generated Scripts History
if st.session_state.generated_scripts:
    st.divider()
    st.header("📜 Generated Scripts History")
    
    for i, item in enumerate(st.session_state.generated_scripts[:5], 1):
        with st.expander(f"Script {i}: {item['query'][:60]}..."):
            st.markdown("**Original Request:**")
            st.write(item['query'])
            st.markdown("**Generated Script:**")
            st.code(item['script'], language="python")
            st.download_button(
                label="📥 Download",
                data=item['script'],
                file_name=f"playwright_script_{i}.py",
                mime="text/x-python",
                key=f"download_{i}"
            )

# Query History
if st.session_state.query_history:
    st.divider()
    st.header("📜 Query History")
    
    for i, item in enumerate(st.session_state.query_history[:5], 1):
        with st.expander(f"Query {i}: {item['query'][:50]}..."):
            if item['result'].get("response"):
                st.markdown("**Orchestrator Response:**")
                st.write(item['result']['response'][:500] + "...")
            if item['result'].get("rag_result"):
                st.markdown("**RAG Answer:**")
                st.write(item['result']['rag_result'].get('answer', '')[:500] + "...")

# Footer
st.divider()
st.markdown("---")
st.markdown(
    """
    <div style='text-align: center; color: gray;'>
        <p>Agentic RAG System with Orchestrator Agent | Built with Streamlit & Google ADK</p>
        <p><small>Uses Google Gemini API for orchestration and script generation</small></p>
    </div>
    """,
    unsafe_allow_html=True
)
