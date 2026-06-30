import { Component, type ReactNode } from 'react';

interface Props {
  /** 変わると（タブ切替など）エラー状態をリセットして再描画を試みる。 */
  resetKey: string | number;
  children: ReactNode;
}
interface State {
  error: Error | null;
}

/** マスタ各エディタを包む境界。あるタブの描画が例外を投げても、アプリ全体を
 *  白画面にせず、そのタブだけ穏当なメッセージを出して他タブの操作を保つ。
 *  resetKey（選択中マスタ）が変わると自動で復帰する。 */
export class EditorErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidUpdate(prev: Props) {
    if (prev.resetKey !== this.props.resetKey && this.state.error) {
      this.setState({ error: null });
    }
  }

  render() {
    if (this.state.error) {
      return (
        <div className="editor-error" role="alert">
          <p>このマスタの表示中にエラーが発生しました。他のタブは引き続き利用できます。</p>
          <pre>{this.state.error.message}</pre>
        </div>
      );
    }
    return this.props.children;
  }
}
