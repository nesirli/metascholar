# ruff: noqa: E402  # st.set_page_config must be first Streamlit command
import streamlit as st
st.set_page_config(page_title="MetaScholar", page_icon="🦠")

from metascholar.config import settings

from metascholar.rag.rag_init import assistant
from metascholar.rag.judge import evaluate_relevance
from metascholar.app.dashboard import show_dashboard
from metascholar.app.db_query import save_llm_call
from metascholar.app.db_feedback import save_feedback


def check_auth():
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False

    if st.session_state.authenticated:
        return True

    _, center, _ = st.columns([1, 2, 1])
    with center:
        with st.container(border=True):
            username = st.text_input("Username", placeholder="demo")
            password = st.text_input("Password", type="password", placeholder="••••••••")
            if st.button("Login", use_container_width=True):
                if username == settings.app_username and password == settings.app_password:
                    st.session_state.authenticated = True
                    st.rerun()
                else:
                    st.error("Invalid username or password")
    return False


def show_chat():
    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "active_chat_start" not in st.session_state:
        st.session_state.active_chat_start = -1
    if "new_chat" not in st.session_state:
        st.session_state.new_chat = False

    st.title("MetaScholar")
    st.caption(
        "Try: *What computational pipelines are used for metagenomics analysis?*, "
        "*How does diet affect the gut microbiome?*, "
        "*What tools are used for metagenomic binning?*"
    )

    # Determine which messages to show
    if st.session_state.new_chat:
        visible = []
    else:
        start = st.session_state.active_chat_start
        if start >= 0:
            visible = st.session_state.messages[start : start + 2]
        else:
            visible = st.session_state.messages

    if not visible:
        st.caption("Ask a question to start a new chat.")
    else:
        for msg in visible:
            with st.chat_message(msg["role"]):
                st.write(msg["content"])
                if (msg["role"] == "assistant"
                        and not msg["content"].strip().lower().startswith("i don't know")
                        and msg.get("sources")):
                    with st.expander("References"):
                        for i, src in enumerate(msg["sources"], 1):
                            st.caption(
                                f"[{i}] {src['title']} "
                                f"({src.get('year', '?')}, {src.get('journal', '?')}) — "
                                f"PMID {src['pmid']}"
                            )
                if msg.get("conversation_id"):
                    col1, col2, _ = st.columns([1, 1, 4])
                    with col1:
                        if st.button("👍", key=f"up_{msg['conversation_id']}"):
                            save_feedback(msg["conversation_id"], "user", score=1)
                            st.toast("Thanks!")
                    with col2:
                        if st.button("👎", key=f"down_{msg['conversation_id']}"):
                            save_feedback(msg["conversation_id"], "user", score=-1)
                            st.toast("Thanks for the feedback!")

    if query := st.chat_input("Ask about metagenomics literature..."):
        st.session_state.new_chat = False
        st.session_state.active_chat_start = -1  # show all when asking new
        st.session_state.messages.append({"role": "user", "content": query})

        with st.chat_message("user"):
            st.write(query)

        with st.chat_message("assistant"):
            with st.spinner("Searching and generating answer..."):
                result = assistant.query(query)
                conversation_id = save_llm_call(result)
                with st.spinner("Evaluating relevance..."):
                    relevance, explanation = evaluate_relevance(query, result.answer)
                    save_feedback(conversation_id, "judge", relevance=relevance, explanation=explanation)

            st.write(result.answer)

            if not result.answer.strip().lower().startswith("i don't know") and result.sources:
                with st.expander("References"):
                    for i, src in enumerate(result.sources, 1):
                        st.caption(
                            f"[{i}] {src['title']} "
                            f"({src.get('year', '?')}, {src.get('journal', '?')}) — "
                            f"PMID {src['pmid']}"
                        )

            col1, col2, _ = st.columns([1, 1, 4])
            with col1:
                if st.button("👍", key=f"up_{conversation_id}"):
                    save_feedback(conversation_id, "user", score=1)
                    st.toast("Thanks!")
            with col2:
                if st.button("👎", key=f"down_{conversation_id}"):
                    save_feedback(conversation_id, "user", score=-1)
                    st.toast("Thanks for the feedback!")

            st.session_state.messages.append({
                "role": "assistant",
                "content": result.answer,
                "sources": result.sources,
                "conversation_id": conversation_id,
            })
            st.rerun()


if check_auth():
    with st.sidebar:
        if st.button("Logout"):
            st.session_state.authenticated = False
            st.session_state.messages = []
            st.session_state.active_chat_start = -1
            st.session_state.new_chat = False
            st.rerun()

        st.divider()

        if st.button("+ New chat", use_container_width=True):
            st.session_state.new_chat = True
            st.session_state.active_chat_start = -1
            st.rerun()

        if st.session_state.get("messages"):
            st.caption("Chats")
            if st.button("All chats", use_container_width=True):
                st.session_state.new_chat = False
                st.session_state.active_chat_start = -1
                st.rerun()
            # Group into Q&A pairs (user at even indices, assistant at odd)
            msgs = st.session_state.messages
            for i in range(0, len(msgs) - 1, 2):
                question = msgs[i]["content"][:60]
                is_active = st.session_state.active_chat_start == i
                if st.button(question, key=f"chat_{i}", use_container_width=True,
                             type="primary" if is_active else "secondary"):
                    st.session_state.new_chat = False
                    st.session_state.active_chat_start = i
                    st.rerun()

    chat_tab, dash_tab = st.tabs(["Chat", "Dashboard"])

    with chat_tab:
        show_chat()
    with dash_tab:
        show_dashboard()
