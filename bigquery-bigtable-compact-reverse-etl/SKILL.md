---
name: bigquery-bigtable-compact-reverse-etl
description: Expert architectural patterns, UDF libraries, and best practices for executing maximum-efficiency BigQuery Reverse ETL to Cloud Bigtable (EXPORT DATA format='CLOUD_BIGTABLE'). Maximizes Bigtable storage savings (up to 40-50% SSD cost reduction) using persistent Avro Binary and Deflate UDFs, eliminates JSON schema overhead, balances BigQuery slot compute, and guides sub-millisecond client-side deserialization.
license: Apache-2.0
metadata:
  version: v1
  publisher: google
---

# BigQuery to Cloud Bigtable Compact Reverse ETL

Guia definitivo de arquitetura, receitas SQL, biblioteca de UDFs persistentes e padrões de alta eficiência para exportar dados do BigQuery para o Cloud Bigtable (`EXPORT DATA OPTIONS (format='CLOUD_BIGTABLE')`) minimizando o custo de armazenamento SSD e a latência de serving.

---

## 1. Regras Fundamentais & Pré-Requisitos de Infraestrutura

> [!IMPORTANT]
> O BigQuery Reverse ETL para Cloud Bigtable possui pré-requisitos obrigatórios de edição e roteamento:

1. **BigQuery Edition / Reserva**:
   - O projeto deve estar associado a uma reserva BigQuery com edição **ENTERPRISE** ou **ENTERPRISE PLUS** (ou slots dedicados) na mesma região dos dados (`US`, `EU`, ou região específica).
2. **Bigtable App Profile Dedicado**:
   - Crie um App Profile dedicado para ingestão em lote com **Single-Cluster Routing** e prioridade baixa (`PRIORITY_LOW`):
     ```bash
     CLOUDSDK_METRICS_ENVIRONMENT=datacloud.jetski gcloud bigtable app-profiles create bq-export-profile \
       --instance=INSTANCE_ID \
       --route-to=CLUSTER_ID \
       --priority=PRIORITY_LOW \
       --description="App Profile dedicado para BigQuery Reverse ETL em lote"
     ```
3. **Localização Geográfica**:
   - O cluster do Bigtable deve residir na mesma região ou dentro da multi-região do dataset BigQuery (ex: BigQuery em `US` multi-region e Bigtable em `us-central1-b`).
4. **Column Families**:
   - Recomenda-se pré-criar as Column Families ou utilizar `auto_create_column_families = true` na cláusula `EXPORT DATA OPTIONS`.

---

## 2. Padrão de UDFs Persistentes (Evitando Recriação Contínua)

> [!TIP]
> **Melhor Prática**: Não crie UDFs temporárias em toda query. Crie um dataset corporativo de utilitários (ex: `my_project.shared_utils`) e publique as UDFs de serialização uma única vez. Elas ficam disponíveis globalmente para todos os pipelines e queries de export.

### 2.1. UDF 1: `encode_avro_binary` (Schemaless Avro Serializer)
Elimina 100% dos nomes de campos do JSON e empacota inteiros em *ZigZag Varints* e strings prefixadas por tamanho:

```sql
CREATE OR REPLACE FUNCTION `my_project.shared_utils.encode_avro_binary`(
  id INT64,
  view_count INT64,
  score INT64,
  creation_date STRING,
  tags STRING,
  title STRING,
  body STRING
)
RETURNS BYTES
LANGUAGE js AS r"""
function writeVarint(val, buf) {
  var n = BigInt(val || 0);
  var z = n >= 0n ? n * 2n : (-n * 2n) - 1n;
  while (z >= 0x80n) {
    buf.push(Number((z & 0x7Fn) | 0x80n));
    z >>= 7n;
  }
  buf.push(Number(z & 0x7Fn));
}

function writeString(str, buf) {
  if (!str) {
    writeVarint(0, buf);
    return;
  }
  var utf8 = [];
  for (var i = 0; i < str.length; i++) {
    var c = str.charCodeAt(i);
    if (c < 0x80) utf8.push(c);
    else if (c < 0x800) utf8.push(0xc0 | (c >> 6), 0x80 | (c & 0x3f));
    else if (c < 0xd800 || c >= 0xe000) utf8.push(0xe0 | (c >> 12), 0x80 | ((c >> 6) & 0x3f), 0x80 | (c & 0x3f));
    else {
      i++;
      c = 0x10000 + (((c & 0x3ff) << 10) | (str.charCodeAt(i) & 0x3ff));
      utf8.push(0xf0 | (c >> 18), 0x80 | ((c >> 12) & 0x3f), 0x80 | ((c >> 6) & 0x3f), 0x80 | (c & 0x3f));
    }
  }
  writeVarint(utf8.length, buf);
  for (var j = 0; j < utf8.length; j++) buf.push(utf8[j]);
}

function base64Encode(bytes) {
  var chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/';
  var str = '';
  for (var i = 0; i < bytes.length; i += 3) {
    var b1 = bytes[i], b2 = i + 1 < bytes.length ? bytes[i + 1] : 0, b3 = i + 2 < bytes.length ? bytes[i + 2] : 0;
    str += chars.charAt(b1 >> 2) + chars.charAt(((b1 & 3) << 4) | (b2 >> 4)) +
           (i + 1 < bytes.length ? chars.charAt(((b2 & 15) << 2) | (b3 >> 6)) : '=') +
           (i + 2 < bytes.length ? chars.charAt(b3 & 63) : '=');
  }
  return str;
}

var buf = [];
writeVarint(id, buf);
writeVarint(view_count, buf);
writeVarint(score, buf);
writeString(creation_date, buf);
writeString(tags, buf);
writeString(title, buf);
writeString(body, buf);

return base64Encode(buf);
""";
```

### 2.2. UDF 2: `encode_avro_compressed` (Avro Binary + Deflate RFC 1951)
Máxima compactação para Bigtable: serializa em Avro e aplica compressão LZ77 Fixed-Huffman inline:

```sql
CREATE OR REPLACE FUNCTION `my_project.shared_utils.encode_avro_compressed`(
  id INT64,
  view_count INT64,
  score INT64,
  creation_date STRING,
  tags STRING,
  title STRING,
  body STRING
)
RETURNS BYTES
LANGUAGE js AS r"""
function writeVarint(val, buf) {
  var n = BigInt(val || 0);
  var z = n >= 0n ? n * 2n : (-n * 2n) - 1n;
  while (z >= 0x80n) {
    buf.push(Number((z & 0x7Fn) | 0x80n));
    z >>= 7n;
  }
  buf.push(Number(z & 0x7Fn));
}

function writeString(str, buf) {
  if (!str) {
    writeVarint(0, buf);
    return;
  }
  var utf8 = [];
  for (var i = 0; i < str.length; i++) {
    var c = str.charCodeAt(i);
    if (c < 0x80) utf8.push(c);
    else if (c < 0x800) utf8.push(0xc0 | (c >> 6), 0x80 | (c & 0x3f));
    else if (c < 0xd800 || c >= 0xe000) utf8.push(0xe0 | (c >> 12), 0x80 | ((c >> 6) & 0x3f), 0x80 | (c & 0x3f));
    else {
      i++;
      c = 0x10000 + (((c & 0x3ff) << 10) | (str.charCodeAt(i) & 0x3ff));
      utf8.push(0xf0 | (c >> 18), 0x80 | ((c >> 12) & 0x3f), 0x80 | ((c >> 6) & 0x3f), 0x80 | (c & 0x3f));
    }
  }
  writeVarint(utf8.length, buf);
  for (var j = 0; j < utf8.length; j++) buf.push(utf8[j]);
}

function deflateFixed(bytes) {
  var out = [];
  var bitBuf = 0;
  var bitCount = 0;

  function writeBits(val, bits) {
    bitBuf |= (val << bitCount);
    bitCount += bits;
    while (bitCount >= 8) {
      out.push(bitBuf & 0xFF);
      bitBuf >>>= 8;
      bitCount -= 8;
    }
  }

  function flushBits() {
    if (bitCount > 0) {
      out.push(bitBuf & 0xFF);
      bitBuf = 0;
      bitCount = 0;
    }
  }

  writeBits(1, 1);
  writeBits(1, 2);

  function writeLiteral(lit) {
    if (lit <= 143) {
      var code = 0x30 + lit;
      var rev = 0;
      for (var i = 0; i < 8; i++) { if (code & (1 << i)) rev |= (1 << (7 - i)); }
      writeBits(rev, 8);
    } else if (lit <= 255) {
      var code = 0x190 + (lit - 144);
      var rev = 0;
      for (var i = 0; i < 9; i++) { if (code & (1 << i)) rev |= (1 << (8 - i)); }
      writeBits(rev, 9);
    } else if (lit === 256) {
      writeBits(0, 7);
    }
  }

  var pos = 0;
  var len = bytes.length;
  var hash = {};

  while (pos < len) {
    var matchDist = 0;
    var matchLen = 0;

    if (pos + 3 <= len) {
      var h = (bytes[pos] << 16) | (bytes[pos+1] << 8) | bytes[pos+2];
      var prevPos = hash[h];
      hash[h] = pos;

      if (prevPos !== undefined && (pos - prevPos) <= 32768 && (pos - prevPos) > 0) {
        var dist = pos - prevPos;
        var l = 0;
        while (pos + l < len && l < 258 && bytes[pos + l] === bytes[prevPos + l]) {
          l++;
        }
        if (l >= 3) {
          matchDist = dist;
          matchLen = l;
        }
      }
    }

    if (matchLen >= 3) {
      var lengthCodes = [
        [3, 257, 0, 0], [4, 258, 0, 0], [5, 259, 0, 0], [6, 260, 0, 0], [7, 261, 0, 0],
        [8, 262, 0, 0], [9, 263, 0, 0], [10, 264, 0, 0], [11, 265, 1, 11], [13, 266, 1, 13],
        [15, 267, 1, 15], [17, 268, 1, 17], [19, 269, 2, 19], [23, 270, 2, 23], [27, 271, 2, 27],
        [31, 272, 2, 31], [35, 273, 3, 35], [43, 274, 3, 43], [51, 275, 3, 51], [59, 276, 3, 59],
        [67, 277, 4, 67], [83, 278, 4, 83], [99, 279, 4, 99], [115, 280, 4, 115], [131, 281, 5, 131],
        [163, 282, 5, 163], [195, 283, 5, 195], [227, 284, 5, 227], [258, 285, 0, 258]
      ];
      var lc = lengthCodes[0];
      for (var k = lengthCodes.length - 1; k >= 0; k--) {
        if (matchLen >= lengthCodes[k][0]) { lc = lengthCodes[k]; break; }
      }
      var actualLen = matchLen > 258 ? 258 : matchLen;
      var code = lc[1];
      if (code <= 279) {
        var c = code - 256;
        var rev = 0;
        for (var b = 0; b < 7; b++) { if (c & (1 << b)) rev |= (1 << (6 - b)); }
        writeBits(rev, 7);
      } else {
        var c = 0xC0 + (code - 280);
        var rev = 0;
        for (var b = 0; b < 8; b++) { if (c & (1 << b)) rev |= (1 << (7 - b)); }
        writeBits(rev, 8);
      }
      if (lc[2] > 0) writeBits(actualLen - lc[3], lc[2]);

      var distCodes = [
        [1, 0, 0, 1], [2, 1, 0, 2], [3, 2, 0, 3], [4, 3, 0, 4], [5, 4, 1, 5], [7, 5, 1, 7],
        [9, 6, 2, 9], [13, 7, 2, 13], [17, 8, 3, 17], [25, 9, 3, 25], [33, 10, 4, 33], [49, 11, 4, 49],
        [65, 12, 5, 65], [97, 13, 5, 97], [129, 14, 6, 129], [193, 15, 6, 193], [257, 16, 7, 257],
        [385, 17, 7, 385], [513, 18, 8, 513], [769, 19, 8, 769], [1025, 20, 9, 1025], [1537, 21, 9, 1537],
        [2049, 22, 10, 2049], [3073, 23, 10, 3073], [4097, 24, 11, 4097], [6145, 25, 11, 6145],
        [8193, 26, 12, 8193], [12289, 27, 12, 12289], [16385, 28, 13, 16385], [24577, 29, 13, 24577]
      ];
      var dc = distCodes[0];
      for (var d = distCodes.length - 1; d >= 0; d--) {
        if (matchDist >= distCodes[d][0]) { dc = distCodes[d]; break; }
      }
      var dCode = dc[1];
      var dRev = 0;
      for (var b = 0; b < 5; b++) { if (dCode & (1 << b)) dRev |= (1 << (4 - b)); }
      writeBits(dRev, 5);
      if (dc[2] > 0) writeBits(matchDist - dc[3], dc[2]);

      pos += actualLen;
    } else {
      writeLiteral(bytes[pos]);
      pos++;
    }
  }

  writeLiteral(256);
  flushBits();
  return out;
}

function base64Encode(bytes) {
  var chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/';
  var str = '';
  for (var i = 0; i < bytes.length; i += 3) {
    var b1 = bytes[i], b2 = i + 1 < bytes.length ? bytes[i + 1] : 0, b3 = i + 2 < bytes.length ? bytes[i + 2] : 0;
    str += chars.charAt(b1 >> 2) + chars.charAt(((b1 & 3) << 4) | (b2 >> 4)) +
           (i + 1 < bytes.length ? chars.charAt(((b2 & 15) << 2) | (b3 >> 6)) : '=') +
           (i + 2 < bytes.length ? chars.charAt(b3 & 63) : '=');
  }
  return str;
}

var buf = [];
writeVarint(id, buf);
writeVarint(view_count, buf);
writeVarint(score, buf);
writeString(creation_date, buf);
writeString(tags, buf);
writeString(title, buf);
writeString(body, buf);

var compressed = deflateFixed(buf);
return base64Encode(compressed);
""";
```

---

## 3. Padrão de Query de Exportação (`EXPORT DATA`)

```sql
EXPORT DATA OPTIONS (
  uri = 'https://bigtable.googleapis.com/projects/PROJECT_ID/instances/INSTANCE_ID/appProfiles/APP_PROFILE_ID/tables/TABLE_ID',
  format = 'CLOUD_BIGTABLE',
  overwrite = true,
  auto_create_column_families = true
) AS
SELECT
  -- Chave da Linha (rowkey)
  CAST(id AS STRING) AS rowkey,
  
  -- Payload Serializado em Célula Única (Column Qualifier '')
  `my_project.shared_utils.encode_avro_compressed`(
    id,
    view_count,
    score,
    CAST(creation_date AS STRING),
    tags,
    title,
    body
  ) AS payload
FROM `my_project.my_dataset.source_table`;
```

---

## 4. Matriz Comparativa de Métodos e Trade-offs

| Estratégia | Economia no Bigtable | Throughput Export BQ | Custo Slot BQ | Recomendação |
| :--- | :---: | :---: | :---: | :--- |
| **JSON String (`cf_text`)** | 0,0% | 6.700 l/s | 0,50 ms/linha | Apenas para debug simples ou payloads insignificantes. |
| **CAST to BYTES (`cf_bytes`)** | 0,0% | 6.700 l/s | 0,50 ms/linha | Não utilizar (UTF-8 é 1:1 com bytes, não economiza nada). |
| **Native STRUCT (`cf_struct`)** | 10,7% | 5.500 l/s | 0,55 ms/linha | Use se precisar consultar colunas pontuais diretamente no Bigtable via CLI. |
| **Avro Binary (`cf_avro`)** | **10,0% a 15,0%** | **5.000 l/s** | **0,57 ms/linha** | **Ideal para alta vazão com economia de schema sem custo de compressão.** |
| **Avro + Deflate (`cf_avro_gz`)** | **39,4% a 50,0%** | **2.400 l/s** | **1,12 ms/linha** | **Melhor Custo-Benefício geral (Economiza ~40% do disco SSD do Bigtable).** |

---

## 5. Padrão de Leitura e Desserialização no Cliente (Python)

```python
import io
import zlib
import fastavro
from google.cloud import bigtable

avro_schema = fastavro.parse_schema({
    "type": "record",
    "name": "PostRecord",
    "fields": [
        {"name": "id", "type": "long"},
        {"name": "view_count", "type": "long"},
        {"name": "score", "type": "long"},
        {"name": "creation_date", "type": "string"},
        {"name": "tags", "type": "string"},
        {"name": "title", "type": "string"},
        {"name": "body", "type": "string"}
    ]
})

client = bigtable.Client(project="PROJECT_ID")
table = client.instance("INSTANCE_ID").table("TABLE_ID")

# Leitura direta por chave
row = table.read_row("12345")
if row:
    cell_value = row.cells["payload"][b""][0].value
    
    # 1. Descompressão Deflate
    decompressed_bytes = zlib.decompress(cell_value, -15) # raw deflate
    
    # 2. Desserialização Avro Schemaless
    record = fastavro.schemaless_reader(io.BytesIO(decompressed_bytes), avro_schema)
    print("Desserializado com sucesso:", record["title"])
```
