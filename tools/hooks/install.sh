#!/bin/sh
# Points .git/hooks at the hooks in tools/hooks. Each installed hook only calls the versioned one, so later
# changes to tools/hooks apply without installing again. Run from Git Bash: sh tools/hooks/install.sh

cd "$(git rev-parse --show-toplevel)" || exit 1
dir="$(git rev-parse --git-common-dir)/hooks"
mkdir -p "$dir"
for hook in tools/hooks/*; do
	name=$(basename "$hook")
	[ "$name" = install.sh ] && continue
	printf '#!/bin/sh\nexec sh "$(git rev-parse --show-toplevel)/tools/hooks/%s" "$@"\n' "$name" > "$dir/$name"
	chmod +x "$dir/$name"
	echo "installed $dir/$name"
done
