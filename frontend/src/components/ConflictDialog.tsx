interface Props {
  version: number; // server's current version from the 409 detail
  onRebase: () => void;
  onCancel: () => void;
}

export function ConflictDialog({ version, onRebase, onCancel }: Props) {
  return (
    <div role="dialog" className="conflict-dialog">
      <h3>編集が競合しました</h3>
      <p>別の編集が先に保存されました (server version {version})。最新の表に作り直してください。</p>
      <button data-testid="rebase" onClick={onRebase}>
        最新に更新して続ける
      </button>
      <button data-testid="conflict-cancel" onClick={onCancel}>
        キャンセル
      </button>
    </div>
  );
}
