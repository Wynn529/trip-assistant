CSS = """
<style>
  .stApp { background: #f6f5f0; color: #17332c; }
  h1, h2, h3 { color: #17332c; }
  [data-testid="stSidebar"] { background: #e8efe8; }
  .hero { padding: 1.5rem 1.7rem; border-radius: 22px; color: #fff;
          background: linear-gradient(115deg,#173d34,#2d6957); margin-bottom: 1rem; }
  .hero h1 { color: white; margin: 0; font-size: 2.1rem; }
  .hero p { color: #dbebe1; margin: .5rem 0 0; }
  .tag { display:inline-block; background:#dfebe3; color:#245443; padding:.25rem .65rem;
         border-radius:999px; margin:.2rem .25rem .2rem 0; font-size:.85rem; }
  .muted { color:#61756a; font-size:.9rem; }
  @media (max-width: 960px) {
    div[data-testid="stHorizontalBlock"] { flex-direction: column; gap: 1rem; }
    div[data-testid="stColumn"] { width: 100% !important; min-width: 0 !important; flex: 1 1 100% !important; }
    .hero h1 { font-size: 1.7rem; }
  }
</style>
"""
