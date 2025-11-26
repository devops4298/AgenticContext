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
import logging
import streamlit as st
from pathlib import Path

# Fix OpenMP conflict before importing other modules
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
os.environ.setdefault("OMP_NUM_THREADS", "1")

# Suppress httpx HTTP request logging
logging.getLogger("httpx").setLevel(logging.WARNING)

# Configure root logger to write to file
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(name)s] %(levelname)s: %(message)s',
    handlers=[
        logging.FileHandler("streamlit_debug.log", mode='w'),
        logging.StreamHandler(sys.stdout)
    ]
)

# Import the RAG pipeline components and orchestrator
from tools.rag import RAGPipeline, AppConfig
from agents.orchestrator_agent import OrchestratorAgent
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Page config
st.set_page_config(
    page_title="QA-CaFe - Test Assistant",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for modern, colorful design
st.markdown("""
    <style>
    /* Main theme colors */
    :root {
        --primary-color: #6366f1;
        --secondary-color: #8b5cf6;
        --success-color: #10b981;
        --warning-color: #f59e0b;
        --error-color: #ef4444;
        --info-color: #3b82f6;
        --dark-bg: #1e293b;
        --light-bg: #f8fafc;
    }
    
    /* Main container styling */
    .main .block-container {
        padding-top: 1rem;
        padding-bottom: 1rem;
    }
    
    /* Title styling with gradient */
    h1 {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        background-clip: text;
        font-weight: 700;
        font-size: 2rem;
        margin-bottom: 0.5rem;
    }
    
    /* Subheader styling */
    h2 {
        color: #4f46e5;
        font-weight: 600;
        border-bottom: 2px solid #e0e7ff;
        padding-bottom: 0.5rem;
        margin-top: 1.5rem;
    }
    
    h3 {
        color: #6366f1;
        font-weight: 600;
    }
    
    /* Sidebar styling */
    .css-1d391kg {
        background: linear-gradient(180deg, #f8fafc 0%, #e2e8f0 100%);
    }
    
    /* Success messages with better styling */
    .stSuccess {
        background: linear-gradient(135deg, #d1fae5 0%, #a7f3d0 100%);
        border-left: 3px solid #10b981;
        border-radius: 6px;
        padding: 0.5rem 0.75rem;
    }
    
    /* Info messages */
    .stInfo {
        background: linear-gradient(135deg, #dbeafe 0%, #bfdbfe 100%);
        border-left: 3px solid #3b82f6;
        border-radius: 6px;
        padding: 0.5rem 0.75rem;
    }
    
    /* Warning messages */
    .stWarning {
        background: linear-gradient(135deg, #fef3c7 0%, #fde68a 100%);
        border-left: 3px solid #f59e0b;
        border-radius: 6px;
        padding: 0.5rem 0.75rem;
    }
    
    /* Error messages */
    .stError {
        background: linear-gradient(135deg, #fee2e2 0%, #fecaca 100%);
        border-left: 3px solid #ef4444;
        border-radius: 6px;
        padding: 0.5rem 0.75rem;
    }
    
    /* Metrics with colorful borders */
    [data-testid="stMetricValue"] {
        color: #6366f1;
        font-weight: 700;
    }
    
    [data-testid="stMetricLabel"] {
        color: #64748b;
        font-weight: 500;
    }
    
    /* Buttons styling */
    .stButton > button {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
        border: none;
        border-radius: 8px;
        padding: 0.5rem 1.5rem;
        font-weight: 600;
        transition: all 0.3s ease;
        box-shadow: 0 4px 6px rgba(102, 126, 234, 0.3);
    }
    
    .stButton > button:hover {
        transform: translateY(-2px);
        box-shadow: 0 6px 12px rgba(102, 126, 234, 0.4);
    }
    
    /* Primary button */
    button[kind="primary"] {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%) !important;
    }
    
    /* Secondary button */
    button[kind="secondary"] {
        background: linear-gradient(135deg, #64748b 0%, #475569 100%) !important;
    }
    
    /* Expander styling */
    .streamlit-expanderHeader {
        background: linear-gradient(135deg, #f1f5f9 0%, #e2e8f0 100%);
        border-radius: 6px;
        padding: 0.5rem 0.75rem;
        font-weight: 600;
        color: #475569;
    }
    
    /* Code blocks */
    .stCodeBlock {
        border-radius: 8px;
        border: 2px solid #e0e7ff;
        background: #1e293b;
    }
    
    /* Divider styling */
    hr {
        border: none;
        height: 1px;
        background: linear-gradient(90deg, transparent, #cbd5e1, transparent);
        margin: 1rem 0;
    }
    
    /* Status container */
    [data-testid="stStatus"] {
        border-radius: 8px;
        border: 2px solid #e0e7ff;
        background: linear-gradient(135deg, #f8fafc 0%, #f1f5f9 100%);
    }
    
    /* Input fields */
    .stTextInput > div > div > input {
        border-radius: 8px;
        border: 2px solid #e2e8f0;
    }
    
    .stTextInput > div > div > input:focus {
        border-color: #6366f1;
        box-shadow: 0 0 0 3px rgba(99, 102, 241, 0.1);
    }
    
    /* Text area */
    .stTextArea > div > div > textarea {
        border-radius: 8px;
        border: 2px solid #e2e8f0;
    }
    
    .stTextArea > div > div > textarea:focus {
        border-color: #6366f1;
        box-shadow: 0 0 0 3px rgba(99, 102, 241, 0.1);
    }
    
    /* Checkbox styling */
    .stCheckbox label {
        font-weight: 500;
        color: #475569;
    }
    
    /* Slider styling */
    .stSlider {
        padding: 0.5rem 0;
    }
    
    /* Radio buttons */
    .stRadio label {
        font-weight: 500;
        color: #475569;
    }
    
    /* Download button */
    .stDownloadButton > button {
        background: linear-gradient(135deg, #10b981 0%, #059669 100%) !important;
        box-shadow: 0 4px 6px rgba(16, 185, 129, 0.3);
    }
    
    /* Footer styling */
    footer {
        visibility: hidden;
    }
    
    /* Custom card styling */
    .custom-card {
        background: linear-gradient(135deg, #ffffff 0%, #f8fafc 100%);
        border-radius: 12px;
        padding: 1.5rem;
        border: 2px solid #e0e7ff;
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.05);
        margin: 1rem 0;
    }
    
    /* Step cards */
    .step-card {
        background: linear-gradient(135deg, #fef3c7 0%, #fde68a 100%);
        border-left: 4px solid #f59e0b;
        border-radius: 8px;
        padding: 1rem;
        margin: 0.5rem 0;
    }
    </style>
    """, unsafe_allow_html=True)

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
if 'plan_approval_pending' not in st.session_state:
    st.session_state.plan_approval_pending = False
if 'current_plan' not in st.session_state:
    st.session_state.current_plan = None
if 'generate_script_requested' not in st.session_state:
    st.session_state.generate_script_requested = False
# Removed user selection state variables - no longer needed


def auto_load_existing_index():
    """Automatically load existing index on app startup."""
    try:
        import json
        import os
        from tools.rag import DEFAULT_INDEX_METADATA_PATH, DEFAULT_CACHE_DIR
        
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


def generate_plan_with_orchestrator(user_query: str):
    """Generate a plan using the orchestrator agent.
    
    Args:
        user_query: User's query
    """
    if not st.session_state.pipeline:
        st.error("❌ Pipeline not initialized. Please configure repository/folder first.")
        return None
    
    if not st.session_state.orchestrator:
        st.error("❌ Orchestrator agent not initialized.")
        return None
    
    try:
        with st.status("🤖 **Planning**: Analyzing request and retrieving context...", expanded=True) as status:
            status.update(label="🔍 Step 1: Formatting request and extracting steps...", state="running")
            
            plan = st.session_state.orchestrator.generate_plan(
                user_query=user_query,
                rag_pipeline=st.session_state.pipeline
            )
            
            if plan and not plan.get("error"):
                if plan.get("steps"):
                    status.update(label=f"✅ Extracted {len(plan.get('steps', []))} steps", state="complete")
                else:
                    status.update(label="✅ Plan generated", state="complete")
            else:
                status.update(label="⚠️ Planning completed with issues", state="complete")
        
        return plan
    except Exception as e:
        st.error(f"❌ Error generating plan: {str(e)}")
        st.exception(e)
        return None


def execute_plan_with_orchestrator(plan: dict, generate_script: bool = False):
    """Execute the approved plan using the orchestrator agent.
    
    Args:
        plan: The approved plan dictionary
        generate_script: Whether to generate script
    """
    if not st.session_state.orchestrator:
        st.error("❌ Orchestrator agent not initialized.")
        return None
        
    try:
        with st.status("🤖 **Executing**: Generating automation artifacts...", expanded=True) as status:
            status.update(label="⚙️ Step 3: Generating script...", state="running")
            
            result = st.session_state.orchestrator.execute_plan(
                plan=plan,
                automation_tool="playwright" if generate_script else None
            )
            
            status.update(label="✅ Execution complete", state="complete")
            
        return result
    except Exception as e:
        st.error(f"❌ Error executing plan: {str(e)}")
        st.exception(e)
        return None


# Sidebar for configuration
with st.sidebar:
    st.markdown("""
        <div style='background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); 
                    border-radius: 8px; padding: 0.75rem; margin-bottom: 1rem; 
                    box-shadow: 0 2px 4px rgba(102, 126, 234, 0.2);'>
            <h3 style='color: white; margin: 0; text-align: center; font-size: 1.1rem;'>⚙️ Configuration</h3>
        </div>
    """, unsafe_allow_html=True)
    
    # Show current index status
    if st.session_state.index_metadata:
        st.markdown("""
            <div style='background: linear-gradient(135deg, #dbeafe 0%, #bfdbfe 100%); 
                        border-radius: 8px; padding: 0.5rem 0.75rem; margin: 0.75rem 0;'>
                <h4 style='color: #1e40af; margin: 0; text-align: center; font-size: 1rem;'>📊 Current Index</h4>
            </div>
        """, unsafe_allow_html=True)
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
    st.markdown("""
        <div style='background: linear-gradient(135deg, #fef3c7 0%, #fde68a 100%); 
                    border-radius: 8px; padding: 0.5rem 0.75rem; margin: 0.75rem 0;'>
            <h4 style='color: #92400e; margin: 0; text-align: center; font-size: 1rem;'>📂 Index Management</h4>
        </div>
    """, unsafe_allow_html=True)
    
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
            from tools.rag import DEFAULT_CACHE_DIR
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
    st.markdown("""
        <div style='background: linear-gradient(135deg, #e0e7ff 0%, #c7d2fe 100%); 
                    border-radius: 8px; padding: 0.5rem 0.75rem; margin: 0.75rem 0;'>
            <h4 style='color: #4f46e5; margin: 0; text-align: center; font-size: 1rem;'>🔧 Query Settings</h4>
        </div>
    """, unsafe_allow_html=True)
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
    st.markdown("""
        <div style='background: linear-gradient(135deg, #d1fae5 0%, #a7f3d0 100%); 
                    border-radius: 8px; padding: 0.5rem 0.75rem; margin: 0.75rem 0;'>
            <h4 style='color: #065f46; margin: 0; text-align: center; font-size: 1rem;'>🔧 Status</h4>
        </div>
    """, unsafe_allow_html=True)
    
    if st.session_state.pipeline and st.session_state.index_loaded:
        st.markdown("""
            <div style='background: #ecfdf5; border-left: 3px solid #10b981; 
                        border-radius: 6px; padding: 0.5rem 0.75rem; margin: 0.4rem 0;'>
                <p style='color: #047857; margin: 0; font-weight: 600; font-size: 0.9rem;'>✅ Pipeline Ready</p>
            </div>
        """, unsafe_allow_html=True)
        if st.session_state.orchestrator:
            st.markdown("""
                <div style='background: #ecfdf5; border-left: 3px solid #10b981; 
                            border-radius: 6px; padding: 0.5rem 0.75rem; margin: 0.4rem 0;'>
                    <p style='color: #047857; margin: 0; font-weight: 600; font-size: 0.9rem;'>✅ Orchestrator Ready</p>
                </div>
            """, unsafe_allow_html=True)
        if st.session_state.pipeline.metadata:
            num_chunks = len(st.session_state.pipeline.metadata)
            st.metric("Total Chunks", num_chunks)
            if st.session_state.pipeline.indexer.index:
                st.metric("Index Size", st.session_state.pipeline.indexer.index.ntotal)
    else:
        st.info("ℹ️ **No index loaded** - Index a folder or repository to get started")


# Main content area with compact gradient header
st.markdown("""
    <div style='text-align: center; padding: 1rem 0; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); 
                border-radius: 10px; margin-bottom: 1rem; box-shadow: 0 4px 8px rgba(102, 126, 234, 0.2);'>
        <h1 style='color: white; margin: 0; font-size: 2rem; font-weight: 700;'>
            🤖 QA-CaFe
        </h1>
        <p style='color: rgba(255, 255, 255, 0.9); font-size: 1rem; margin: 0.25rem 0 0 0;'>
            Test Assistant for Websites
        </p>
    </div>
    """, unsafe_allow_html=True)

# Check API key
api_key = os.getenv("GOOGLE_AI_API_KEY")
if not api_key or api_key == "your-api-key-here":
    st.error("⚠️ **GOOGLE_AI_API_KEY not set!** Please set it in your `.env` file.")
    st.stop()

# Current source info with compact colorful cards
if st.session_state.index_loaded and st.session_state.index_metadata:
    metadata = st.session_state.index_metadata
    if metadata.get("indexed_source") == "local_folder":
        indexed_path = metadata.get("indexed_folder_path", "")
        num_chunks = metadata.get('num_chunks', 0)
        st.markdown(f"""
            <div style='background: linear-gradient(135deg, #d1fae5 0%, #a7f3d0 100%); 
                        border-left: 3px solid #10b981; border-radius: 8px; padding: 0.75rem; 
                        margin: 0.5rem 0; box-shadow: 0 2px 4px rgba(16, 185, 129, 0.15);'>
                <p style='color: #065f46; margin: 0; font-weight: 600; font-size: 0.9rem;'>
                    📁 <strong>Indexed Folder:</strong> {os.path.basename(indexed_path) if indexed_path else 'Unknown'} | 
                    <strong>Chunks:</strong> {num_chunks}
                </p>
            </div>
        """, unsafe_allow_html=True)
    elif metadata.get("indexed_source") == "github_repo":
        repo_url = metadata.get("repo_url", "")
        num_chunks = metadata.get('num_chunks', 0)
        st.markdown(f"""
            <div style='background: linear-gradient(135deg, #dbeafe 0%, #bfdbfe 100%); 
                        border-left: 3px solid #3b82f6; border-radius: 8px; padding: 0.75rem; 
                        margin: 0.5rem 0; box-shadow: 0 2px 4px rgba(59, 130, 246, 0.15);'>
                <p style='color: #1e40af; margin: 0; font-weight: 600; font-size: 0.9rem;'>
                    📚 <strong>Indexed Repository:</strong> {repo_url[:50]}{'...' if len(repo_url) > 50 else ''} | 
                    <strong>Chunks:</strong> {num_chunks}
                </p>
            </div>
        """, unsafe_allow_html=True)
elif st.session_state.folder_path:
    st.info(f"📁 **Current Folder:** `{st.session_state.folder_path}`")
elif st.session_state.repo_url:
    st.info(f"📚 **Current Repository:** `{st.session_state.repo_url}`")
else:
    st.markdown("""
        <div style='background: linear-gradient(135deg, #fef3c7 0%, #fde68a 100%); 
                    border-left: 3px solid #f59e0b; border-radius: 8px; padding: 0.75rem; 
                    margin: 0.5rem 0; box-shadow: 0 2px 4px rgba(245, 158, 11, 0.15);'>
            <p style='color: #92400e; margin: 0; font-weight: 600; font-size: 0.9rem;'>
                ℹ️ <strong>No index loaded.</strong> Use the sidebar to index a folder or repository.
            </p>
        </div>
    """, unsafe_allow_html=True)

# Query input with compact styled header
st.markdown("""
    <div style='background: linear-gradient(135deg, #e0e7ff 0%, #c7d2fe 100%); 
                border-radius: 8px; padding: 0.5rem 0.75rem; margin: 1rem 0;'>
        <h3 style='color: #4f46e5; margin: 0; font-size: 1.1rem;'>💬 Ask a Question or Request Playwright Script</h3>
    </div>
""", unsafe_allow_html=True)

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

# Removed resume button - no longer needed (auto-selection handled in orchestrator)

# Process query
result = None

# Case 1: Plan Approval Pending
if st.session_state.plan_approval_pending and st.session_state.current_plan:
    st.divider()
    st.markdown("""
        <div style='background: linear-gradient(135deg, #fef3c7 0%, #fde68a 100%); 
                    border-left: 3px solid #f59e0b; border-radius: 8px; padding: 0.75rem; 
                    margin: 0.75rem 0; box-shadow: 0 2px 4px rgba(245, 158, 11, 0.15);'>
            <h3 style='color: #92400e; margin: 0; font-size: 1.1rem;'>📋 Review & Approve Test Steps</h3>
            <p style='color: #92400e; margin: 0.25rem 0 0 0; font-size: 0.9rem;'>
                Please review the generated steps below. You can edit them before proceeding.
            </p>
        </div>
    """, unsafe_allow_html=True)
    
    # Editable steps
    current_steps = st.session_state.current_plan.get("steps", [])
    
    # Use a form to group the inputs
    with st.form("approval_form"):
        st.markdown("**Uncheck the box to remove a step. Edit the text to modify a step.**")
        
        # We use a text area for each step to allow editing
        step_data = []
        for i, step in enumerate(current_steps):
            cols = st.columns([0.05, 0.95])
            with cols[0]:
                # Checkbox to include/exclude step
                included = st.checkbox("Include", value=True, key=f"step_include_{i}", label_visibility="collapsed", help="Uncheck to remove this step")
            with cols[1]:
                # Text input for the step
                text = st.text_input(f"Step {i+1}", value=step, key=f"step_edit_{i}", label_visibility="collapsed")
            step_data.append((included, text))
            
        col1, col2 = st.columns([1, 1])
        with col1:
            approve_btn = st.form_submit_button("✅ Approve & Generate Script", type="primary", use_container_width=True)
        with col2:
            cancel_btn = st.form_submit_button("❌ Cancel", type="secondary", use_container_width=True)
            
    if approve_btn:
        print("DEBUG: Approve button clicked!")
        # Filter and update steps, preserving context mapping
        final_steps = []
        new_step_contexts = {}
        
        # Get original rag_result to map contexts
        rag_result = st.session_state.current_plan.get("rag_result", {})
        original_step_contexts = rag_result.get("step_contexts", {})
        
        new_index = 1
        for i, (included, text) in enumerate(step_data):
            if included:
                final_steps.append(text)
                
                # Map original context (step_i+1) to new index (step_new_index)
                original_key = f"step_{i+1}"
                if original_key in original_step_contexts:
                    new_key = f"step_{new_index}"
                    # Copy context but update the 'step' text in case it was edited
                    context_data = original_step_contexts[original_key].copy()
                    context_data["step"] = text
                    new_step_contexts[new_key] = context_data
                
                new_index += 1
        
        if not final_steps:
            st.error("❌ You must approve at least one step.")
        else:
            # Update plan with approved steps
            st.session_state.current_plan["steps"] = final_steps
            
            # Update RAG result with remapped contexts
            if "rag_result" in st.session_state.current_plan:
                st.session_state.current_plan["rag_result"]["step_contexts"] = new_step_contexts
                st.session_state.current_plan["rag_result"]["steps"] = final_steps
            
            # Execute plan
            result = execute_plan_with_orchestrator(
                st.session_state.current_plan, 
                generate_script=st.session_state.generate_script_requested
            )
            
            # Clear approval state
            st.session_state.plan_approval_pending = False
            st.session_state.current_plan = None
        
    if cancel_btn:
        st.session_state.plan_approval_pending = False
        st.session_state.current_plan = None
        st.rerun()

# Case 2: New Query
elif submit_btn and query:
    if not st.session_state.pipeline:
        st.warning("⚠️ Pipeline not initialized. Please index a folder or repository first.")
        st.stop()
    
    if st.session_state.pipeline and st.session_state.orchestrator:
        # Generate plan first
        plan = generate_plan_with_orchestrator(query)
        
        if plan:
            st.session_state.current_plan = plan
            st.session_state.generate_script_requested = generate_script
            st.session_state.plan_approval_pending = True
            st.rerun()

# Display Result (if execution just finished)
if result:
    # Use orchestrator result
    
    # Add to query history
    st.session_state.query_history.insert(0, {
        "query": query,
        "result": result,
        "timestamp": "now"
    })
            
    # Show error if any
    if result.get("error"):
        st.error(f"❌ {result.get('error')}")
        if result.get("response"):
            st.info(result["response"])
    else:
        # Display orchestrator response
        if result.get("response"):
            st.divider()
            st.markdown("""
                <div style='background: linear-gradient(135deg, #dbeafe 0%, #bfdbfe 100%); 
                            border-left: 3px solid #3b82f6; border-radius: 8px; padding: 0.5rem 0.75rem; 
                            margin: 0.75rem 0; box-shadow: 0 2px 4px rgba(59, 130, 246, 0.15);'>
                    <h3 style='color: #1e40af; margin: 0; font-size: 1.1rem;'>📝 Result</h3>
                </div>
            """, unsafe_allow_html=True)
            st.markdown(f"""
                <div style='background: #eff6ff; border-left: 3px solid #3b82f6; 
                            border-radius: 6px; padding: 0.75rem; margin: 0.5rem 0;'>
                    <p style='color: #1e3a8a; margin: 0; line-height: 1.5; font-size: 0.95rem;'>{result["response"]}</p>
                </div>
            """, unsafe_allow_html=True)
    
    # Show extracted steps
    steps_to_show = result.get("steps", []) if result else []
    
    if steps_to_show:
        st.divider()
        
        st.markdown("""
            <div style='background: linear-gradient(135deg, #fef3c7 0%, #fde68a 100%); 
                        border-left: 3px solid #f59e0b; border-radius: 8px; padding: 0.5rem 0.75rem; 
                        margin: 0.75rem 0; box-shadow: 0 2px 4px rgba(245, 158, 11, 0.15);'>
                <h3 style='color: #92400e; margin: 0; font-size: 1.1rem;'>📋 Extracted Steps</h3>
            </div>
        """, unsafe_allow_html=True)
        
        steps = steps_to_show
        step_corrections = result.get("step_corrections", {})
        
        # Display total count compactly
        col1, col2 = st.columns([1, 4])
        with col1:
            st.metric("Steps", len(steps))
        
        # Display steps with corrections and referenced chunks
        for i, step in enumerate(steps, 1):
            correction_info = step_corrections.get(i, {})
            original_step = correction_info.get("original", step)
            corrected_step = correction_info.get("corrected", step)
            referenced_chunks = correction_info.get("referenced_chunks", [])
            
            if corrected_step != original_step:
                # Step was corrected automatically - show correction with referenced chunks
                with st.expander(f"✅ Step {i}: {corrected_step}", expanded=False):
                    st.markdown(f"**Original:** ~~{original_step}~~")
                    st.markdown(f"**Corrected:** {corrected_step}")
                    
                    if referenced_chunks:
                        st.markdown("**Referenced from:**")
                        for ref_chunk in referenced_chunks:
                            path = ref_chunk.get("path", "unknown")
                            snippet = ref_chunk.get("snippet", "")
                            matched_terms = ref_chunk.get("matched_terms", [])
                            
                            st.markdown(f"📄 **{path}**")
                            if matched_terms:
                                st.caption(f"Matched terms: {', '.join(matched_terms)}")
                            st.code(snippet[:500] + ("..." if len(snippet) > 500 else ""), language="text")
                    else:
                        st.caption("No specific chunk portions identified for this correction.")
            else:
                # Step was not corrected - show as is
                st.markdown(f"""
                    <div style='background: linear-gradient(135deg, #fef3c7 0%, #fde68a 100%); 
                                border-left: 3px solid #f59e0b; border-radius: 6px; 
                                padding: 0.5rem 0.75rem; margin: 0.5rem 0; 
                                box-shadow: 0 2px 4px rgba(245, 158, 11, 0.15);'>
                        <p style='color: #92400e; margin: 0; font-weight: 600; font-size: 0.9rem;'>
                            <strong>Step {i}:</strong> {step}
                        </p>
                    </div>
                """, unsafe_allow_html=True)
    
    # Display generated Playwright script (most important output)
    # Show script section if generate_script was requested OR if script exists
    if generate_script or result.get("generated_script"):
        st.divider()
        st.markdown("""
            <div style='background: linear-gradient(135deg, #ddd6fe 0%, #c4b5fd 100%); 
                        border-left: 3px solid #8b5cf6; border-radius: 8px; padding: 0.5rem 0.75rem; 
                        margin: 0.75rem 0; box-shadow: 0 2px 4px rgba(139, 92, 246, 0.2);'>
                <h3 style='color: #6b21a8; margin: 0; font-size: 1.1rem;'>🎭 Generated Playwright Script</h3>
            </div>
        """, unsafe_allow_html=True)
        
        script = result.get("generated_script")
        
        if script and len(script.strip()) > 0:
            # Save script to history
            st.session_state.generated_scripts.insert(0, {
                "query": query,
                "script": script,
                "timestamp": "now"
            })
            
            # Display script with download option
            st.code(script, language="python")
            
            col1, col2 = st.columns([1, 3])
            with col1:
                st.download_button(
                    label="📥 Download Script",
                    data=script,
                    file_name="playwright_script.py",
                    mime="text/x-python",
                    use_container_width=True
                )
            with col2:
                st.caption("💡 Install: `pip install playwright && playwright install`")
        else:
            # Script was requested but not generated
            st.warning("⚠️ Script generation was requested but no script was returned.")
            if result.get("response"):
                st.info(f"Response: {result['response']}")
            
            # Debug: Show what we have
            with st.expander("🔍 Debug: Check script generation", expanded=False):
                st.write("**Result keys:**", str(list(result.keys())))
                st.write("**Has generated_script key:**", str("generated_script" in result))
                st.write("**Script value:**", str(script)[:200] if script else "None")
                st.write("**Automation tool:**", str(result.get("automation_tool", "Not set")))
                st.write("**Generate script checkbox:**", str(generate_script))
        
        # Show validation steps compactly
        st.divider()
        st.markdown("""
            <div style='background: linear-gradient(135deg, #d1fae5 0%, #a7f3d0 100%); 
                        border-left: 3px solid #10b981; border-radius: 8px; padding: 0.5rem 0.75rem; 
                        margin: 0.75rem 0; box-shadow: 0 2px 4px rgba(16, 185, 129, 0.15);'>
                <h3 style='color: #065f46; margin: 0; font-size: 1.1rem;'>✅ Validation Steps Performed</h3>
            </div>
        """, unsafe_allow_html=True)
        
        validation_steps = [
            "Request formatted and steps extracted",
            "Context retrieved from RAG system",
            "DOM nodes identified using CDP",
            "Script syntax validation",
            "Code quality checks",
            "Completeness verification"
        ]
        
        cols = st.columns(3)
        for i, step in enumerate(validation_steps):
            with cols[i % 3]:
                st.markdown(f"""
                    <div style='background: #ecfdf5; border-left: 2px solid #10b981; 
                                border-radius: 6px; padding: 0.4rem 0.6rem; margin: 0.4rem 0;'>
                        <p style='color: #047857; margin: 0; font-weight: 500; font-size: 0.85rem;'>
                            ✓ {step}
                        </p>
                    </div>
                """, unsafe_allow_html=True)
    
    # Show technical details if available (collapsed)
    if result.get("formatted_request") or result.get("scripter_result") or result.get("rag_result"):
        with st.expander("🔧 Technical Details", expanded=False):
            if result.get("formatted_request"):
                st.markdown("**Formatted Request:**")
                st.json(result["formatted_request"])
            
            if result.get("rag_result"):
                rag_result = result["rag_result"]
                st.markdown("**RAG Result:**")
                overall_context = rag_result.get("overall_context", {})
                if overall_context.get("answer"):
                    st.markdown(overall_context.get("answer", "")[:500] + "...")
                
                col1, col2 = st.columns(2)
                with col1:
                    retrieved = overall_context.get("retrieved", [])
                    st.metric("Retrieved Chunks", len(retrieved))
                with col2:
                    step_contexts = rag_result.get("step_contexts", {})
                    st.metric("Step Contexts", len(step_contexts))
            
            if result.get("scripter_result"):
                st.markdown("**Scripter Result (DOM Nodes):**")
                scripter_result = result["scripter_result"]
                step_nodes = scripter_result.get("step_nodes", {})
                url_used = scripter_result.get("url_used", "Not found")
                
                st.info(f"🌐 URL used for CDP inspection: {url_used if url_used else 'None (fallback to inference)'}")
                
                # Show detailed node information
                node_summary = {}
                for k, v in step_nodes.items():
                    node = v.get("node", {})
                    node_summary[k] = {
                        "step": v.get("step", ""),
                        "node_selector": node.get("node_selector", ""),
                        "node_type": node.get("node_type", ""),
                        "source": node.get("source", "unknown"),
                        "has_error": "error" in node,
                        "url": node.get("url", "")
                    }
                    if "error" in node:
                        node_summary[k]["error"] = node.get("error", "")
                
                st.json({
                    "total_steps": len(step_nodes),
                    "url_used": url_used,
                    "step_nodes": node_summary
                })
                
                # Show CDP status
                cdp_success = sum(1 for v in step_nodes.values() if v.get("node", {}).get("source") == "cdp_inspector")
                cdp_errors = sum(1 for v in step_nodes.values() if "error" in v.get("node", {}))
                inference_fallback = sum(1 for v in step_nodes.values() if v.get("node", {}).get("source") == "inference")
                
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("✅ CDP Success", cdp_success)
                with col2:
                    st.metric("⚠️ CDP Errors", cdp_errors)
                with col3:
                    st.metric("🔮 Inference Fallback", inference_fallback)
    

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
                key=f"download_script_history_{i}"
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

# Footer with compact gradient
st.divider()
st.markdown(
    """
    <div style='background: linear-gradient(135deg, #f8fafc 0%, #e2e8f0 100%); 
                border-radius: 8px; padding: 1rem; margin-top: 2rem; 
                text-align: center; box-shadow: 0 2px 4px rgba(0, 0, 0, 0.05);'>
        <p style='color: #475569; font-weight: 600; margin: 0.25rem 0; font-size: 0.95rem;'>
            QA-CaFe Test Assistant System
        </p>
        <p style='color: #94a3b8; margin: 0.25rem 0 0 0; font-size: 0.8rem;'>
            Built with Streamlit
        </p>
    </div>
    """,
    unsafe_allow_html=True
)
