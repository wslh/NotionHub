using System;
using System.Collections;
using System.Collections.Generic;
using System.Globalization;
using System.Text;

// Minimal JSON reader/writer for the native messaging protocol.
// Avoids taking a dependency on System.Web.Extensions / Newtonsoft.
internal static class Json
{
    // ---------- reading ----------

    public static Dictionary<string, object> Parse(string text)
    {
        int i = 0;
        object value = ParseValue(text, ref i);
        return value as Dictionary<string, object> ?? new Dictionary<string, object>();
    }

    private static object ParseValue(string s, ref int i)
    {
        SkipWs(s, ref i);
        if (i >= s.Length) return null;
        char c = s[i];
        switch (c)
        {
            case '{': return ParseObject(s, ref i);
            case '[': return ParseArray(s, ref i);
            case '"': return ParseString(s, ref i);
            case 't': Expect(s, ref i, "true"); return true;
            case 'f': Expect(s, ref i, "false"); return false;
            case 'n': Expect(s, ref i, "null"); return null;
            default: return ParseNumber(s, ref i);
        }
    }

    private static Dictionary<string, object> ParseObject(string s, ref int i)
    {
        var result = new Dictionary<string, object>(StringComparer.Ordinal);
        i++; // '{'
        SkipWs(s, ref i);
        if (i < s.Length && s[i] == '}') { i++; return result; }
        while (i < s.Length)
        {
            SkipWs(s, ref i);
            string key = ParseString(s, ref i);
            SkipWs(s, ref i);
            if (i < s.Length && s[i] == ':') i++;
            SkipWs(s, ref i);
            result[key] = ParseValue(s, ref i);
            SkipWs(s, ref i);
            if (i < s.Length && s[i] == ',') { i++; continue; }
            if (i < s.Length && s[i] == '}') { i++; break; }
            break;
        }
        return result;
    }

    private static List<object> ParseArray(string s, ref int i)
    {
        var result = new List<object>();
        i++; // '['
        SkipWs(s, ref i);
        if (i < s.Length && s[i] == ']') { i++; return result; }
        while (i < s.Length)
        {
            result.Add(ParseValue(s, ref i));
            SkipWs(s, ref i);
            if (i < s.Length && s[i] == ',') { i++; continue; }
            if (i < s.Length && s[i] == ']') { i++; break; }
            break;
        }
        return result;
    }

    private static string ParseString(string s, ref int i)
    {
        var sb = new StringBuilder();
        i++; // opening quote
        while (i < s.Length)
        {
            char c = s[i++];
            if (c == '"') break;
            if (c == '\\' && i < s.Length)
            {
                char esc = s[i++];
                switch (esc)
                {
                    case '"': sb.Append('"'); break;
                    case '\\': sb.Append('\\'); break;
                    case '/': sb.Append('/'); break;
                    case 'b': sb.Append('\b'); break;
                    case 'f': sb.Append('\f'); break;
                    case 'n': sb.Append('\n'); break;
                    case 'r': sb.Append('\r'); break;
                    case 't': sb.Append('\t'); break;
                    case 'u':
                        if (i + 4 <= s.Length)
                        {
                            sb.Append((char)Convert.ToInt32(s.Substring(i, 4), 16));
                            i += 4;
                        }
                        break;
                    default: sb.Append(esc); break;
                }
                continue;
            }
            sb.Append(c);
        }
        return sb.ToString();
    }

    private static object ParseNumber(string s, ref int i)
    {
        int start = i;
        while (i < s.Length && "+-.eE0123456789".IndexOf(s[i]) >= 0) i++;
        string token = s.Substring(start, i - start);
        double d;
        if (double.TryParse(token, NumberStyles.Float, CultureInfo.InvariantCulture, out d))
            return d;
        return 0d;
    }

    private static void Expect(string s, ref int i, string word)
    {
        if (i + word.Length <= s.Length && string.CompareOrdinal(s, i, word, 0, word.Length) == 0)
            i += word.Length;
        else
            i = s.Length;
    }

    private static void SkipWs(string s, ref int i)
    {
        while (i < s.Length && (s[i] == ' ' || s[i] == '\t' || s[i] == '\n' || s[i] == '\r')) i++;
    }

    // ---------- writing ----------

    // Alternating key/value pairs: Json.Obj("ok", true, "path", "x")
    public static string Obj(params object[] kv)
    {
        var sb = new StringBuilder("{");
        for (int i = 0; i + 1 < kv.Length; i += 2)
        {
            if (i > 0) sb.Append(',');
            sb.Append(EncodeString(Convert.ToString(kv[i], CultureInfo.InvariantCulture)));
            sb.Append(':');
            sb.Append(Encode(kv[i + 1]));
        }
        sb.Append('}');
        return sb.ToString();
    }

    public static string Err(string message)
    {
        return Obj("ok", false, "error", message);
    }

    private static string Encode(object value)
    {
        if (value == null) return "null";
        if (value is bool) return (bool)value ? "true" : "false";
        if (value is int || value is long) return Convert.ToString(value, CultureInfo.InvariantCulture);
        if (value is double || value is float)
            return ((double)Convert.ChangeType(value, typeof(double), CultureInfo.InvariantCulture))
                   .ToString("R", CultureInfo.InvariantCulture);
        if (value is string) return EncodeString((string)value);

        var dict = value as IDictionary;
        if (dict != null)
        {
            var sb = new StringBuilder("{");
            bool first = true;
            foreach (DictionaryEntry entry in dict)
            {
                if (!first) sb.Append(',');
                first = false;
                sb.Append(EncodeString(Convert.ToString(entry.Key, CultureInfo.InvariantCulture)));
                sb.Append(':');
                sb.Append(Encode(entry.Value));
            }
            sb.Append('}');
            return sb.ToString();
        }

        var list = value as IEnumerable;
        if (list != null && !(value is string))
        {
            var sb = new StringBuilder("[");
            bool first = true;
            foreach (object item in list)
            {
                if (!first) sb.Append(',');
                first = false;
                sb.Append(Encode(item));
            }
            sb.Append(']');
            return sb.ToString();
        }

        return EncodeString(Convert.ToString(value, CultureInfo.InvariantCulture));
    }

    private static string EncodeString(string s)
    {
        var sb = new StringBuilder("\"");
        foreach (char c in s ?? "")
        {
            switch (c)
            {
                case '"': sb.Append("\\\""); break;
                case '\\': sb.Append("\\\\"); break;
                case '\b': sb.Append("\\b"); break;
                case '\f': sb.Append("\\f"); break;
                case '\n': sb.Append("\\n"); break;
                case '\r': sb.Append("\\r"); break;
                case '\t': sb.Append("\\t"); break;
                default:
                    if (c < 0x20) sb.Append("\\u").Append(((int)c).ToString("x4"));
                    else sb.Append(c);
                    break;
            }
        }
        sb.Append('"');
        return sb.ToString();
    }
}
