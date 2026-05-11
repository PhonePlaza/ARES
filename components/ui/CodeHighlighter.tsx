"use client";

import { useCallback, useMemo } from "react";
import Editor from "react-simple-code-editor";

// Prism.js core + languages
import Prism from "prismjs";
import "prismjs/components/prism-javascript";
import "prismjs/components/prism-java";
import "prismjs/components/prism-markup"; // XML/HTML

interface CodeHighlighterProps {
    code: string;
    onCodeChange?: (code: string) => void;
    language?: "javascript" | "java" | "xml" | "markup";
    readOnly?: boolean;
    className?: string;
    style?: React.CSSProperties;
}

/**
 * Reusable code editor/viewer with syntax highlighting
 * 
 * - Editable mode: for Script Editor (/editor)
 * - Read-only mode: for APK Analysis (/analysis)
 * 
 * Uses react-simple-code-editor + Prism.js for highlighting
 */
export default function CodeHighlighter({
    code,
    onCodeChange,
    language = "javascript",
    readOnly = false,
    className = "",
    style = {},
}: CodeHighlighterProps) {
    // Map language to Prism grammar
    const grammar = useMemo(() => {
        const lang = language === "xml" ? "markup" : language;
        return Prism.languages[lang] || Prism.languages.javascript;
    }, [language]);

    const prismLanguage = language === "xml" ? "markup" : language;

    // Highlighting function
    const highlight = useCallback(
        (code: string) => Prism.highlight(code, grammar, prismLanguage),
        [grammar, prismLanguage]
    );

    if (readOnly) {
        // Read-only mode: just render highlighted code (no editor overhead)
        return (
            <div className={`code-viewer-readonly ${className}`} style={style}>
                <pre className={`language-${prismLanguage}`} style={{ margin: 0, background: "transparent" }}>
                    <code
                        className={`language-${prismLanguage}`}
                        dangerouslySetInnerHTML={{ __html: highlight(code) }}
                    />
                </pre>
            </div>
        );
    }

    // Editable mode: full editor
    return (
        <div className={`code-editor-container ${className}`} style={style}>
            <Editor
                value={code}
                onValueChange={onCodeChange || (() => { })}
                highlight={highlight}
                padding={16}
                textareaId="code-editor"
                textareaClassName="code-editor-textarea"
                style={{
                    fontFamily: "'Geist Mono', 'Fira Code', Consolas, Monaco, monospace",
                    fontSize: "0.875rem",
                    lineHeight: "1.7",
                    minHeight: "100%",
                    background: "transparent",
                    ...style,
                }}
            />
        </div>
    );
}

/**
 * Detect language from file extension
 */
export function detectLanguage(filePath: string): "javascript" | "java" | "xml" {
    const ext = filePath.split(".").pop()?.toLowerCase() || "";

    switch (ext) {
        case "java":
            return "java";
        case "xml":
        case "html":
            return "xml";
        case "js":
        case "ts":
        case "jsx":
        case "tsx":
            return "javascript";
        default:
            return "java"; // Default for decompiled APK files
    }
}
