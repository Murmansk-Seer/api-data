"""Publish a build without overwriting concurrent source changes or force-pushing."""
import argparse
import subprocess


def git(*args, check=True):
    return subprocess.run(["git", *args], check=check, capture_output=True,
                          text=True, encoding="utf-8")


def publish(base, branch, attempts=3):
    for attempt in range(attempts):
        git("fetch", "--no-tags", "origin", f"refs/heads/{branch}")
        remote = git("rev-parse", "FETCH_HEAD").stdout.strip()
        if git("merge-base", "--is-ancestor", remote, "HEAD", check=False).returncode:
            # A history-only sync is safe to integrate. Any actual change needs
            # a fresh build, even if Git could merge it without a conflict.
            if git("diff", "--quiet", base, remote, check=False).returncode:
                raise RuntimeError("Remote content changed during build; rerun from latest branch. Release was not published.")
            git("merge", "--no-edit", remote)
        result = git("push", "origin", f"HEAD:refs/heads/{branch}", check=False)
        if result.returncode == 0:
            return
        print(result.stderr)
        print(f"Push attempt {attempt + 1}/{attempts} failed; rechecking remote.")
    raise RuntimeError("Push failed after bounded retries; Release was not published.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", required=True)
    parser.add_argument("--branch", required=True)
    args = parser.parse_args()
    publish(args.base, args.branch)
