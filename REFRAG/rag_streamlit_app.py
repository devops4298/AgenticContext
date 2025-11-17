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
if 'query_history' not in st.session_state:
    st.session_state.query_history = []
if 'generated_scripts' not in st.session_state:
    st.session_state.generated_scripts = []


def initialize_pipeline_from_folder(folder_path: str, force_reindex: bool = False):
    """Initialize RAG pipeline from a local folder path."""
    try:
        with st.spinner("Initializing RAG pipeline from folder..."):
            cfg = AppConfig()
            pipeline = RAGPipeline(cfg)
            
            if force_reindex:
                with st.spinner(f"Indexing folder: {folder_path}..."):
                    pipeline.ingest_folder(folder_path, reindex=True)
                st.success(f"✅ Folder indexed successfully! ({len(pipeline.metadata)} chunks)")
                st.session_state.index_loaded = True
            else:
                cache_loaded = pipeline.load_from_cache(expected_folder_path=folder_path)
                if cache_loaded and pipeline.metadata and pipeline.indexer.index:
                    st.success(f"✅ Loaded cache: {len(pipeline.metadata)} chunks")
                    st.session_state.index_loaded = True
                else:
                    if cache_loaded == False:
                        st.info(f"📂 Cache doesn't match folder '{folder_path}'. Re-indexing...")
                    else:
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
            # First, get context from RAG system if needed
            rag_context = None
            if generate_script or "automate" in user_query.lower() or "playwright" in user_query.lower():
                # Query RAG for relevant context
                with st.spinner("Retrieving context from indexed documents..."):
                    rag_result = st.session_state.pipeline.query(user_query, top_k=40)
                    rag_context = rag_result
            
            # Use orchestrator to coordinate agents and generate script if needed
            result = st.session_state.orchestrator.orchestrate(
                user_query=user_query,
                rag_context=rag_context,
                rag_pipeline=st.session_state.pipeline
            )
            
            return result
    except Exception as e:
        st.error(f"❌ Error orchestrating request: {str(e)}")
        st.exception(e)
        return None


# Sidebar for configuration
with st.sidebar:
    st.header("⚙️ Configuration")
    
    # Input mode selection
    input_mode = st.radio(
        "Input Mode",
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
            load_btn = st.button("📂 Index Folder", type="primary", use_container_width=True)
        with col2:
            reindex_btn = st.button("🔄 Reindex", use_container_width=True)
        
        if load_btn or reindex_btn:
            st.session_state.pipeline = None
            st.session_state.index_loaded = False
            st.session_state.repo_url = None
            if folder_path:
                st.session_state.folder_path = folder_path
                if os.path.exists(folder_path) and os.path.isdir(folder_path):
                    initialize_pipeline_from_folder(folder_path, force_reindex=reindex_btn)
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
            load_btn = st.button("📂 Load/Index", use_container_width=True)
        with col2:
            reindex_btn = st.button("🔄 Reindex", use_container_width=True)
        
        if load_btn:
            st.session_state.pipeline = None
            st.session_state.index_loaded = False
            st.session_state.folder_path = None
            if repo_url:
                initialize_pipeline(repo_url, force_reindex=False)
            else:
                st.error("Please enter a repository URL")
        
        if reindex_btn:
            st.session_state.pipeline = None
            st.session_state.index_loaded = False
            st.session_state.folder_path = None
            if repo_url:
                initialize_pipeline(repo_url, force_reindex=True)
            else:
                st.error("Please enter a repository URL")
    
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
    st.subheader("📊 Status")
    if st.session_state.pipeline:
        st.success("✅ Pipeline Ready")
        if st.session_state.orchestrator:
            st.success("✅ Orchestrator Agent Ready")
        if st.session_state.index_loaded or st.session_state.pipeline.metadata:
            num_chunks = len(st.session_state.pipeline.metadata)
            st.metric("Total Chunks", num_chunks)
            if st.session_state.pipeline.indexer.index:
                st.metric("Index Size", st.session_state.pipeline.indexer.index.ntotal)
    else:
        st.warning("⚠️ Pipeline Not Loaded")


# Main content area
st.title("🤖 Agentic RAG - Playwright Script Generator")
st.markdown("**Intelligent RAG system with orchestrator agent for context understanding and Playwright automation script generation**")

# Check API key
api_key = os.getenv("GOOGLE_AI_API_KEY")
if not api_key or api_key == "your-api-key-here":
    st.error("⚠️ **GOOGLE_AI_API_KEY not set!** Please set it in your `.env` file.")
    st.stop()

# Current source info
if st.session_state.folder_path:
    st.info(f"📁 Current Folder: `{st.session_state.folder_path}`")
elif st.session_state.repo_url:
    st.info(f"📚 Current Repository: `{st.session_state.repo_url}`")

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
