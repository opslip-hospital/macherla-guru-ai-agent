"""Hugging Face Spaces entry point for the isolated GPU worker."""
from gradio_app import demo

if __name__ == "__main__":
    demo.queue(max_size=4).launch()
